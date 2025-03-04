import os
import logging
from typing import Any, Dict, List, Tuple
from datetime import datetime, timezone
from concurrent.futures import ProcessPoolExecutor, as_completed
from langchain_core.embeddings import Embeddings
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from chatnerd.stores.store_factory import StoreFactory
from chatnerd.langchain.llm_factory import LLMFactory
from chatnerd.tools.event_emitter import EventEmitter
from chatnerd.config import Config

DEFAULT_CHUNK_SIZE = 1_000
DEFAULT_CHUNK_OVERLAP = 100

_RUN_TASKS_LIMIT = 1_000  # Maximum number of tasks to run in a single call to run()


class DocumentEmbedder(EventEmitter):
    config: Dict[str, Any] = {}

    def __init__(self, nerd_config: Dict[str, Any]):
        super().__init__()
        self.config = nerd_config

    # @staticmethod
    def run(
        self, documents: List[Document], limit: int = _RUN_TASKS_LIMIT
    ) -> Tuple[List[str], List[any]]:
        logging.debug("Running document embedder...")

        if len(documents) == 0:
            logging.debug("No documents to embed")
            return [], []

        # Limit number of tasks to run
        if not limit or not 0 < limit < _RUN_TASKS_LIMIT:
            limit = _RUN_TASKS_LIMIT
        if len(documents) > limit:
            logging.warning(
                f"Number of documents to embeed cut to limit {limit} (out of {len(documents)})"
            )
            documents = documents[:limit]

        # Emit start event (show progress bar in UI)
        self.emit("start", len(documents))

        # Maximum workers depending on vector store thread safety configuration
        store = StoreFactory(self.config).get_vector_store()
        if store.is_thread_safe():
            max_workers = 2 if os.cpu_count() > 4 else 1
        else:
            max_workers = 1
        store.close()

        results = []
        errors = []
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            response_futures = [
                executor.submit(self.split_and_embed_document, document)
                for document in documents
            ]

            for response_future in as_completed(response_futures):
                try:
                    response = response_future.result()
                    if response:
                        results.append(response)  # append the id of the source document

                        try:
                            self.emit(
                                "write",
                                f"✔ {response}",
                            )
                        except:
                            pass
                except Exception as err:
                    errors.append(err)
                finally:
                    self.emit("update")

        self.emit("end")
        return results, errors

    @staticmethod
    def split_and_embed_document(document: Document) -> str:
        config = Config().get_project_config()
        embeddings: Embeddings = LLMFactory(config).get_embedding_function()

        chunk_splitter_config = {
            "separators": ["\n\n", "\n", ".", ",", " "],
            "keep_separator": False,
            "chunk_overlap": DEFAULT_CHUNK_OVERLAP,
            "chunk_size": DEFAULT_CHUNK_SIZE,
            "add_start_index": True,
        } | config["splitter"]

        try:
            # Get max sequence length from the embedding model
            max_seq_length = (
                embeddings.model_kwargs.get("max_seq_length")
                or embeddings.max_seq_length
            )
            if not max_seq_length:
                max_seq_length = DEFAULT_CHUNK_SIZE
                logging.warning(
                    "Could not get max_seq_length from embedding model, using default value"
                )

            # fix chunk_size: It must be less than the model max sequence
            chunk_splitter_config["chunk_size"] = min(
                chunk_splitter_config["chunk_size"],
                max_seq_length,
            )
        except Exception as e:
            logging.warning(
                f"Error getting max_seq_length: {str(e)}, using default value"
            )
            chunk_splitter_config["chunk_size"] = DEFAULT_CHUNK_SIZE

        # Add created_at metadata
        created_at_utc_iso = datetime.now(timezone.utc).isoformat()
        document.metadata["created_at"] = created_at_utc_iso

        chunks = DocumentEmbedder.split_documents(
            [document],
            splitter_kwargs=chunk_splitter_config,
        )

        store_factory = StoreFactory(config)
        chunks_database = store_factory.get_vector_store(embeddings=embeddings)

        try:
            # Embed and store chunk documents
            chunk_ids = chunks_database.add_documents(documents=chunks)
        except Exception as e:
            logging.error(f"Error embedding documents: {str(e)}")
            raise

        # Save source document in status store
        with store_factory.get_status_store() as status_store:
            status_store.add_studied_document(
                id=document.metadata.get("source", None),
                source=document.metadata.get("source", None),
                page_content=document.page_content,
                metadata=document.metadata,
            )

        return document.metadata.get("source", None)

    @staticmethod
    def split_documents(
        documents: List[Document],
        splitter_kwargs: Dict[str, Any] = {},
    ) -> List[Document]:
        """
        Load documents and split in chunks
        """

        splitter_kwargs = {
            "separators": ["\n\n", "\n", ".", ",", " "],
            "chunk_size": DEFAULT_CHUNK_SIZE,
            "chunk_overlap": DEFAULT_CHUNK_OVERLAP,
            "keep_separator": False,
        } | splitter_kwargs

        text_splitter = RecursiveCharacterTextSplitter(**splitter_kwargs)

        texts, metadatas = [], []
        for document in documents:
            texts.append(document.page_content)
            metadatas.append(document.metadata)

        chunks = text_splitter.create_documents(texts, metadatas=metadatas)

        return chunks
