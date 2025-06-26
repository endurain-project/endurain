from fastapi.responses import FileResponse
import os

import core.config as core_config


def return_frontend_index(path: str):
    return FileResponse("/app/frontend/dist/" + path)


def return_user_img_path(user_img: str):
    file_path = f"/app/backend/{core_config.USER_IMAGES_DIR}/" + user_img
    if not os.path.isfile(file_path):
        return None
    return FileResponse(file_path)


def return_server_img_path(server_img: str):
    file_path = f"/app/backend/{core_config.SERVER_IMAGES_DIR}/" + server_img
    if not os.path.isfile(file_path):
        return None
    return FileResponse(file_path)
