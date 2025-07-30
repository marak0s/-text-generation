import json
from pathlib import Path
import gradio as gr

_users = {}
current_user = None


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
                return gr.update(visible=False), gr.update(visible=True), ''
            return gr.update(), gr.update(), '<span style="color:red">Invalid credentials</span>'

        login_btn.click(do_login, [username, password], [login_block, interface_block, msg])
    return

