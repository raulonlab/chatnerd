from pathlib import Path
from typing import Optional
from typing_extensions import Annotated
import typer
from typer.core import TyperGroup
from click import Context
from tqdm import tqdm
from chatnerd.lib.enums import LogColors
from chatnerd.config import Config


_global_config = Config.instance()


LimitOption = Annotated[
    Optional[int],
    typer.Option(
        "--limit",
        "-l",
        help="Limit the maximum number of items to process per run. If not specified, use default limit of 1000 items.",
    ),
]


DirectoryFilterArgument = Annotated[
    Optional[str],
    typer.Argument(
        help="Only process directories containing the string. If not specified, process all directories."
    ),
]


DryRunOption = Annotated[
    Optional[bool],
    typer.Option(
        "--dry-run",
        "-d",
        help="Run command in dry mode (get the expected response without running the task)",
    ),
]


class OrderedCommandsTyperGroup(TyperGroup):
    def list_commands(self, ctx: Context):
        """Return list of commands in the order appear."""
        return list(self.commands)  # get commands using self.commands


class TqdmHolder:
    _tqdm: Optional[tqdm] = None
    _init_kwargs: dict = {}

    def __init__(self, **kwargs):
        self._init_kwargs = kwargs

    def start(self, *args, **kwargs):
        if self._tqdm:
            self._tqdm.close()

        # move positional argument "total" to kwargs
        if args and len(args) > 0:
            kwargs["total"] = int(args[0])

        self._tqdm = tqdm(**{**self._init_kwargs, **kwargs})

    def update(self, *args, **kwargs):
        if not self._tqdm:
            return

        self._tqdm.update(*args, **kwargs)

    def write(self, *args, **kwargs):
        if not self._tqdm:
            return

        self._tqdm.write(*args, **kwargs)

    def close(self):
        if not self._tqdm:
            return

        self._tqdm.close()
        self._tqdm = None


# validate and prompt to confirm the active project
def validate_confirm_active_project(skip_confirmation: bool = True):
    if not _global_config.get_active_project():
        typer.echo(
            "No active project set. Please set an active project first. See chatnerd project --help. "
        )
        raise typer.Abort()

    active_project = _global_config.get_active_project()

    if skip_confirmation:
        typer.echo(
            f"Using project {LogColors.BOLDPROJECT}{active_project}{LogColors.ENDC}..."
        )
    else:
        prompt_response = prompt_active_project(
            active_project=active_project,
            project_base_path=_global_config.get_project_base_path(),
        )
        if not prompt_response:
            raise typer.Abort()


def prompt_active_project(active_project: str, project_base_path: Path):
    if not project_base_path.exists():
        typer.echo(
            f"The active project {LogColors.BOLDPROJECT}{active_project}{LogColors.ENDC} does not exist. Please create it first."
        )
        raise typer.Abort()
    else:
        prompt_text = f"The active project is {LogColors.BOLDPROJECT}{active_project}{LogColors.ENDC}"
        return typer.confirm(
            f"{prompt_text}... do you want to continue?", default=True, abort=False
        )


def grep_match(pattern: str, *args):
    """
    Returns True if a pattern matches any of the args values (in a case-insensitive manner)
    """
    if not pattern:
        return True

    pattern = pattern.lower()
    for arg in args:
        if pattern in str(arg).lower():
            return True
    return False
