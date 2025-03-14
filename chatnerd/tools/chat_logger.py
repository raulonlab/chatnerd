from typing import List, Optional, Dict, Any
from pathlib import Path
from datetime import datetime
from chatnerd.config import Config

CHAT_LOG_FILE = "chats.log"
CONFIG_KEYS_TO_LOG = ["default_model", "retriever", "chat_chain"]


class ChatLogger:
    logs_path: Path
    config: Config

    def __init__(self, config: Config = None):
        if config:
            self.config = config
        else:
            self.config = Config.instance()

        self.logs_path = Path(self.config.get_project_base_path(), "logs")
        if not self.logs_path.exists():
            self.logs_path.mkdir(parents=True, exist_ok=True)

    def append_to_log(self, key: str, value: str) -> None:
        log_file_path = self.get_current_log_file_path()

        try:
            with open(log_file_path, "a", encoding="utf-8") as file_handler:
                file_handler.write(f"\n{key}: {value}\n")
        except Exception as e:
            print(f"Error appending to log:\n{e}")

    def log(
        self,
        question: str,
        answer: str,
        documents: Optional[List[any]] = [],
    ) -> None:
        log_file_path = self.get_current_log_file_path()

        try:
            reduced_documents = [
                {"source": doc.metadata["source"], "page_content": doc.page_content}
                for doc in documents
            ]

            config_changes_dict = self.config.read_project_config(
                self.config.get_project_base_path()
            )

            config_changes_dict = {
                key: value
                for key, value in config_changes_dict.items()
                if key in CONFIG_KEYS_TO_LOG
            }

            log_dict = {
                "created_at": datetime.utcnow().strftime("%d/%m/%Y %H:%M:%S"),
                "question": question,
                "answer": answer,
                "documents": reduced_documents,
                "project_name": self.config.ACTIVE_PROJECT,
                "project_config": config_changes_dict,
            }

            project_config_formatted_string = self.format_config(
                log_dict["project_config"]
            )
            documents_formatted_string = self.format_documents(reduced_documents)

            with open(log_file_path, "a", encoding="utf-8") as file_handler:
                log_lines = [
                    f"\n{log_dict['created_at']} ------------------------------------",
                    f"Q: \n{log_dict['question']}",
                    f"A: \n{log_dict['answer']}",
                    "project_config:",
                    f"{project_config_formatted_string}",
                    "documents:",
                    f"{documents_formatted_string}",
                ]

                file_handler.write("\n".join(log_lines))
        except Exception as e:
            print(f"Error writing log:\n{e}")

    def get_current_log_file_path(self) -> Path:
        utc_now = datetime.utcnow()
        today_prefix = utc_now.strftime("%Y%m%d")
        return Path(self.logs_path, f"{today_prefix}_{CHAT_LOG_FILE}")

    @classmethod
    def format_config(
        cls, project_config: Dict[str, Any], line_prefix: Optional[str] = "  - "
    ) -> str:
        result_string = ""
        # if project_config.get("system_prompt"):
        #     result_string += f"{line_prefix}system_prompt: {cls.one_line(project_config['system_prompt'])}\n"
        if project_config.get("default_model"):
            result_string += (
                f"{line_prefix}default_model: {project_config['default_model']}\n"
            )
        if project_config.get("retriever"):
            result_string += f"{line_prefix}retriever:\n"
            result_string += f"  {line_prefix}search_type: {project_config['retriever']['search_type']}\n"
            result_string += f"  {line_prefix}search_kwargs: {project_config['retriever']['search_kwargs']}\n"
        if project_config.get("chat_chain"):
            result_string += (
                f"{line_prefix}chat_chain: {project_config['chat_chain']}\n"
            )

        return result_string

    @classmethod
    def format_documents(
        cls, documents: List[dict], line_prefix: Optional[str] = "  - "
    ) -> str:
        result_string = ""
        for doc in documents:
            result_string += f"{line_prefix}{doc.get('source', '')}\n"
            result_string += (
                f"{line_prefix}{cls.one_line(doc.get('page_content', ''))}\n"
            )

        return result_string

    @staticmethod
    def one_line(text: str) -> str:
        return text.replace("\n", " ").replace("\r", " ").strip()
