from typing import Optional
from typing_extensions import Annotated
import typer
import logging
import yaml
from pathlib import Path
from rich.console import Console
from rich.syntax import Syntax
from chatnerd.config import Config
from chatnerd.cli import cli_projects, cli_utils, cli_db
from chatnerd.lib.helpers import get_filtered_directories
from chatnerd.tools.chat_logger import ChatLogger


app = typer.Typer(cls=cli_utils.OrderedCommandsTyperGroup, no_args_is_help=True)

# Import commands from other modules
# app.registered_commands += ....app.registered_commands


# Default command
@app.callback(invoke_without_command=True)
def main(ctx: typer.Context):
    if ctx.invoked_subcommand is None:
        app.show_help(ctx)

    if ctx.command == "test":
        print("Running test command...")


@app.command(
    "study",
    help="Start studying documents (embed and store documents in vector DB)",
)
def study_command(
    directory_filter: cli_utils.DirectoryFilterArgument = None,
    limit: cli_utils.LimitOption = None,
):
    cli_utils.validate_confirm_active_project()

    try:
        source_directories = get_filtered_directories(
            directory_filter=directory_filter,
            base_path=Path(
                Config.instance().get_project_base_path(),
                Config._PROJECT_SOURCE_DOCUMENTS_DIRECTORYNAME,
            ),
        )

        from chatnerd.document_loaders.document_loader import DocumentLoader

        document_loader = DocumentLoader(
            project_config=Config.instance().get_project_config(),
            source_directories=source_directories,
        )

        tqdm_holder = cli_utils.TqdmHolder(desc="Loading documents", ncols=80)
        document_loader.on("start", tqdm_holder.start)
        document_loader.on("update", tqdm_holder.update)
        document_loader.on("end", tqdm_holder.close)

        document_loader_results, document_loader_errors = document_loader.run(
            limit=limit
        )

        tqdm_holder.close()
        logging.info(
            f"{len(document_loader_results)} documents loaded successfully with {len(document_loader_errors)} errors...."
        )

        if len(document_loader_errors) > 0:
            logging.error("Error loading documents", exc_info=document_loader_errors[0])
            return

        from chatnerd.langchain.document_embedder import DocumentEmbedder

        document_embedder = DocumentEmbedder(Config.instance().get_project_config())

        tqdm_holder = cli_utils.TqdmHolder(desc="Embedding documents", ncols=80)
        document_embedder.on("start", tqdm_holder.start)
        document_embedder.on("update", tqdm_holder.update)
        document_embedder.on("end", tqdm_holder.close)
        document_embedder.on("write", tqdm_holder.write)

        document_embedder_results, document_embedder_errors = document_embedder.run(
            documents=document_loader_results,
            limit=limit,
        )

        tqdm_holder.close()
        logging.info(
            f"{len(document_embedder_results)} documents embedded successfully with {len(document_embedder_errors)} errors...."
        )

        if len(document_embedder_errors) > 0:
            logging.error(
                "Error embedding documents", exc_info=document_embedder_errors[0]
            )

    except Exception as e:
        logging.error(
            "Error studying sources. Try to load the sources separately with the option --source. See chatnerd add --help."
        )
        raise e
    except SystemExit:
        raise typer.Abort()


@app.command("chat", help="Start a chat session with your active project")
def chat_command(
    query: Annotated[
        Optional[str],
        typer.Argument(
            help="Send a one-off query to your active project and exit. If not specified, runs in interactive mode."
        ),
    ] = None,
):
    cli_utils.validate_confirm_active_project()

    from chatnerd.chat import chat

    chat(query=query)


@app.command(
    "retrieve",
    help="Retrieve relevant documents of a query and optionally generate a summary of the documents.",
)
def retrieve_command(
    query: Annotated[
        str,
        typer.Argument(help="Query used to retrieve relevant documents."),
    ] = None,
    summary: Annotated[
        Optional[bool],
        typer.Option(
            "--summary",
            "-s",
            help="Enable / disable generating a summary of the retrieved documents",
        ),
    ] = False,
):
    cli_utils.validate_confirm_active_project()

    from chatnerd.retrieve import retrieve

    retrieve(query=query, with_summary=summary)


@app.command("review", help="Append a review value to the last chat log")
def review_command(
    review_value: Annotated[
        Optional[int],
        typer.Argument(
            help="Value of the review in the range [1, 5]",
        ),
    ] = None,
):
    if not review_value:
        review_value_response = typer.prompt(
            "Review of the last chat iteration [1..5]",
            type=int,
        )
        review_value = int(review_value_response)

    if review_value < 1:
        review_value = 1
    elif review_value > 5:
        review_value = 5

    chat_logger = ChatLogger()
    chat_logger.append_to_log("review", review_value)


@app.command("env", help="Print the current value of environment variables")
def env_command():

    console = Console()

    syntax = Syntax(
        "\n".join(
            [
                "# Current environment variables",
                "# See more info in https://github.com/raulonlab/chatnerd/blob/main/.env_example",
                str(Config.instance()),
            ]
        ),
        "ini",
        line_numbers=False,
    )  # , theme="monokai"
    console.print(syntax)


@app.command(
    "config", help="Print the active project configuration (chatnerd.config.yml)"
)
def config_command(
    section: Annotated[
        Optional[str],
        typer.Argument(help="Print only a specific section of the config"),
    ] = None,
):

    project_config = Config.instance().get_project_config()

    if section:
        if section in project_config:
            project_config = {section: project_config[section]}
        else:
            logging.error(f"Section '{section}' not found in the active project config")
            return

    config_yaml = yaml.safe_dump(
        project_config,
        stream=None,
        default_flow_style=False,
        sort_keys=False,
    )

    syntax = Syntax(
        "\n".join(
            [
                "# Active configuration {section_suffix}".format(
                    section_suffix=f" - {section}" if section else ""
                ),
                "# See more info in https://github.com/raulonlab/chatnerd/blob/main/chatnerd/chatnerd.config.yml",
                config_yaml,
            ]
        ),
        "yaml",
        line_numbers=False,
    )  # , theme="monokai"

    console = Console()
    console.print(syntax)


app.add_typer(
    cli_projects.app,
    name="project",
    help="Manage projects: create, activate, deactivate, list and remove",
)

app.add_typer(
    cli_db.app,
    name="db",
    help="View and manage the local DBs",
    epilog="* These commands require an active project environment.",
)
