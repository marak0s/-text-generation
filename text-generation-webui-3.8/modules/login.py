import json
from pathlib import Path
import yaml
import gradio as gr

from modules import shared, ui

_users = {}
current_user = None


def get_user_settings_path(user: str | None = None) -> Path:
    """Return the settings.yaml path for the given user."""
    user = user or current_user or 'anonymous'
    return Path(f'user_data/sessions/{user}/settings.yaml')


def load_user_settings(user: str) -> None:
    """Load settings for the given user and apply to the interface."""
    settings_path = get_user_settings_path(user)
    if settings_path.exists():
        try:
            with open(settings_path, 'r', encoding='utf-8') as f:
                new_settings = yaml.safe_load(f.read()) or {}
            shared.settings.update(new_settings)
            ui_updates = ui.apply_interface_values(new_settings)
            for name, update in zip(ui.list_interface_input_elements(), ui_updates):
                if name in shared.gradio:
                    shared.gradio[name].update(update)
        except Exception:
            pass


def load_users():
    global _users
    users_file = Path('user_data/users.json')
    if users_file.exists():
        with open(users_file, 'r', encoding='utf-8') as f:
            _users = json.load(f)
    else:
        _users = {}
    return _users


def verify_user(username: str, password: str) -> bool:
    users = load_users()
    return users.get(username) == password


def create_login_ui(login_block, interface_block):
    with login_block:
        username = gr.Textbox(label='Username')
        password = gr.Textbox(label='Password', type='password')
        login_btn = gr.Button('Login')
        msg = gr.HTML()

        def do_login(u, p):
            global current_user
            if verify_user(u, p):
                current_user = u
                load_user_settings(u)
                return gr.update(visible=False), gr.update(visible=True), ''
            return gr.update(), gr.update(), '<span style="color:red">Invalid credentials</span>'

        (login_btn.click(do_login, [username, password], [login_block, interface_block, msg])
                  .then(None, None, None, js='() => {window.dispatchEvent(new Event("resize"));}'))
    return

