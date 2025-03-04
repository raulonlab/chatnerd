from typing import Any, Dict, Optional
from operator import itemgetter
from langchain_core.language_models import BaseLanguageModel
from langchain_core.output_parsers import StrOutputParser, NumberedListOutputParser
from langchain_core.runnables import (
    RunnableParallel,
    RunnablePassthrough,
    RunnableLambda,
    Runnable,
)

# from langchain.chains.combine_documents import create_stuff_documents_chain
from chatnerd.stores.store_factory import StoreFactory
from chatnerd.langchain.llm_factory import LLMFactory
from chatnerd.langchain.summarizer import Summarizer
from chatnerd.langchain.chain_runnables import (
    retrieve_relevant_documents_runnable,
    rerank_documents_runnable,
    get_parent_documents_runnable,
    get_source_documents_runnable,
    combine_documents_runnable,
)
from chatnerd.langchain.prompt_factory import PromptFactory


DEFAULT_CHAT_PROMPT = """
<context>
{context}
</context>

Question: {question}
"""


class ChainFactory:
    config: Dict[str, Any] = {}

    def __init__(self, config: Dict[str, Any]):
        self.config = config

    # Source: https://levelup.gitconnected.com/3-query-expansion-methods-implemented-using-langchain-to-improve-your-rag-81078c1330cd
    def get_chat_chain(self) -> Runnable:
        embeddings = LLMFactory(config=self.config).get_embedding_function()

        store_factory = StoreFactory(self.config)
        retrieve_store = store_factory.get_vector_store(embeddings=embeddings)

        retriever = retrieve_store.as_retriever(**self.config["retriever"])

        llm, prompt_type = LLMFactory(config=self.config).get_model()

        chat_system_prompt: str = self.config["prompts"].get("chat_system_prompt", None)
        chat_human_prompt: str = self.config["prompts"].get(
            "chat_human_prompt", DEFAULT_CHAT_PROMPT
        )
        chat_system_prompt = chat_system_prompt.replace("\n", " ").strip(". ")

        qa_prompt = PromptFactory.build_prompt_template(
            system_prompt=chat_system_prompt,
            human_prompt=chat_human_prompt,
            prompt_type=prompt_type,
            input_variables=["context", "question"],
        )

        chat_chain_config = self.config.get("chat_chain", None)
        if isinstance(chat_chain_config, str) and chat_chain_config in self.config:
            chat_chain_config = self.config.get(chat_chain_config, None)

        if not isinstance(chat_chain_config, dict):
            raise ValueError(
                f"Invalid value in 'chat_chain' configuration: {chat_chain_config}"
            )

        reranker_config = self.config.get("reranker", None)
        if not isinstance(reranker_config, dict):
            raise ValueError(
                f"Invalid value in 'reranker' configuration: {reranker_config}"
            )

        question_expansion_chain = self.get_question_expansion_chain(
            chat_chain_config, llm, prompt_type
        )

        retrieve_relevant_documents = RunnableParallel(
            documents={
                "question": RunnablePassthrough(),
                "documents": question_expansion_chain
                | retrieve_relevant_documents_runnable.bind(
                    retriever=retriever, **chat_chain_config
                ),
            }
            | rerank_documents_runnable.bind(
                use_cross_encoding_rerank=chat_chain_config.get(
                    "use_cross_encoding_rerank", True
                ),
                **reranker_config,
            )
            | get_parent_documents_runnable.bind(
                store=retrieve_store, **chat_chain_config
            ),
            question=RunnablePassthrough(),
        )

        combine_documents_in_context = RunnableParallel(
            context=itemgetter("documents") | combine_documents_runnable,
            question=itemgetter("question"),
            documents=itemgetter("documents"),
        )

        get_results = RunnableParallel(
            result=qa_prompt | llm | StrOutputParser(),
            source_documents=itemgetter("documents"),
        )

        chain = retrieve_relevant_documents | combine_documents_in_context | get_results

        return chain

    def get_retrieve_chain(self, with_summary: Optional[bool] = False) -> Runnable:
        llm_factory = LLMFactory(config=self.config)
        embeddings = llm_factory.get_embedding_function()

        store_factory = StoreFactory(self.config)
        retrieve_store = store_factory.get_vector_store(embeddings=embeddings)

        retriever = retrieve_store.as_retriever(**self.config["retriever"])

        llm, prompt_type = llm_factory.get_model()

        retrieve_chain_config = self.config.get("retrieve_chain", None)
        if (
            isinstance(retrieve_chain_config, str)
            and retrieve_chain_config in self.config
        ):
            retrieve_chain_config = self.config.get(retrieve_chain_config, None)

        if not isinstance(retrieve_chain_config, dict):
            raise ValueError(
                f"Invalid value in 'retrieve_chain' configuration: {retrieve_chain_config}"
            )

        reranker_config = self.config.get("reranker", None)
        if not isinstance(reranker_config, dict):
            raise ValueError(
                f"Invalid value in 'reranker' configuration: {reranker_config}"
            )

        question_expansion_chain = self.get_question_expansion_chain(
            retrieve_chain_config, llm, prompt_type
        )

        summarize_llm, summarize_prompt_type = llm_factory.get_summarize_model()
        summarize_chain = Summarizer(
            self.config, summarize_llm, summarize_prompt_type
        ).get_chain()

        retrieve_relevant_documents = RunnableParallel(
            documents={
                "question": RunnablePassthrough(),
                "documents": question_expansion_chain
                | retrieve_relevant_documents_runnable.bind(
                    retriever=retriever, **retrieve_chain_config
                ),
            }
            | rerank_documents_runnable.bind(
                use_cross_encoding_rerank=retrieve_chain_config.get(
                    "use_cross_encoding_rerank", True
                ),
                **reranker_config,
            ),
            question=RunnablePassthrough(),
        )

        get_results = RunnableParallel(
            question=itemgetter("question"),
            documents=itemgetter("documents")
            | get_parent_documents_runnable.bind(
                store=retrieve_store, **retrieve_chain_config
            ),
        )

        chain = retrieve_relevant_documents | get_results

        if with_summary:
            chain = chain | RunnablePassthrough.assign(
                summary=itemgetter("documents")
                | get_source_documents_runnable.bind(
                    store_factory=store_factory, **retrieve_chain_config
                )
                | summarize_chain
            )

        return chain

    # Generate similar questions from original query using LLM
    # Source: https://levelup.gitconnected.com/3-query-expansion-methods-implemented-using-langchain-to-improve-your-rag-81078c1330cd
    def get_question_expansion_chain(
        self,
        chain_config: Dict[str, str],
        llm: Optional[BaseLanguageModel] = None,
        prompt_type: Optional[str] = None,
    ) -> Runnable:
        if not chain_config:
            raise ValueError("No chain_config provided")
        elif not isinstance(chain_config, dict):
            raise ValueError(f"Invalid chain_config received: {chain_config}")

        if not llm:
            llm, prompt_type = LLMFactory(config=self.config).get_model(is_chat=False)

        n_expanded_questions = chain_config.get("n_expanded_questions", None)
        if not n_expanded_questions or n_expanded_questions < 1:
            return RunnableLambda(lambda input: [input])

        output_parser = NumberedListOutputParser()

        prompt = self.config["prompts"].get("find_expanded_questions_prompt", None)
        if not prompt:
            raise ValueError(
                "Invalid value in 'find_expanded_questions_prompt' configuration"
            )

        question_expansion_prompt = PromptFactory.build_prompt_template(
            human_prompt=prompt,
            prompt_type=prompt_type,
            input_variables=["text"],
            partial_variables={
                "n_expanded_questions": n_expanded_questions,
            },
        )

        question_expansion_chain = RunnableParallel(
            {
                "expanded_questions": question_expansion_prompt | llm | output_parser,
                "question": RunnablePassthrough(),
            }
        ) | RunnableLambda(
            lambda input: [input["question"], *input["expanded_questions"]]
        )

        return question_expansion_chain

    # def get_retrieval_qa_chain(self) -> Runnable:
    #     embeddings = LLMFactory(config=self.config).get_embedding_function()

    #     store_factory = StoreFactory(self.config)
    #     retrieve_store = store_factory.get_vector_store(embeddings=embeddings)

    #     retriever = retrieve_store.as_retriever(**self.config["retriever"])
    #     llm, prompt_type = LLMFactory(config=self.config).get_model()

    #     chat_system_prompt: str = self.config["prompts"].get("chat_system_prompt", None)
    #     chat_human_prompt: str = self.config["prompts"].get(
    #         "chat_human_prompt", DEFAULT_CHAT_PROMPT
    #     )

    #     retrieval_qa_prompt = PromptFactory.build_prompt_template(
    #         system_prompt=chat_system_prompt,
    #         human_prompt=chat_human_prompt,
    #         prompt_type=prompt_type,
    #         input_variables=["context", "question"],
    #     )

    #     qa = create_stuff_documents_chain(
    #         llm=llm,
    #         chain_type="stuff",
    #         retriever=retriever,
    #         return_source_documents=True,
    #         chain_type_kwargs={
    #             "verbose": False,
    #             "prompt": retrieval_qa_prompt,
    #         },
    #     )

    #     return qa
