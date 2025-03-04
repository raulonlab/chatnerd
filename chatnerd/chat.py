import os
from typing import Dict, Optional
from rich import print
from rich.markup import escape
from rich.panel import Panel
from langchain_core.tracers.stdout import ConsoleCallbackHandler
from chatnerd.langchain.chain_factory import ChainFactory
from chatnerd.tools.chat_logger import ChatLogger
from chatnerd.config import Config


_global_config = Config.instance()


def chat(query: Optional[str] = None) -> None:
    project_config = _global_config.get_project_config()

    chat_chain = ChainFactory(project_config).get_chat_chain()
    chat_logger = ChatLogger()

    interactive = not query
    print()
    if interactive:
        print("Type your query below and press Enter.")
        print("Type 'exit' or 'quit' or 'q' to exit the application.\n")

    while True:
        print("[bold]Q: ", end="", flush=True)
        if interactive:
            query = input()
        else:
            print(escape(query))
        print()
        if query.strip() in ["exit", "quit", "q"]:
            print("Exiting...\n")
            break
        print("[bold]A:", end="", flush=True)

        callbacks = []
        if _global_config.VERBOSE > 1:
            callbacks.append(ConsoleCallbackHandler())

        output = chat_chain.invoke(query, config={"callbacks": callbacks})

        if isinstance(output, Dict) and "result" in output:
            response_string = output.get("result", "")
            source_documents = output.get("source_documents", [])
        else:
            response_string = output
            source_documents = []

        print(f"[bright_cyan]{escape(response_string)}[/bright_cyan]\n")
        project_base_path = _global_config.get_project_base_path()
        for doc in source_documents:
            source, content = doc.metadata["source"], doc.page_content
            relative_source = os.path.relpath(source, project_base_path)
            print(
                Panel(
                    f"[bright_blue]...{escape(relative_source)}[/bright_blue]\n\n{escape(content)}"
                )
            )
        print()

        chat_logger.log(query, response_string, source_documents)

        if not interactive:
            break
