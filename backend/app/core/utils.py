from fastapi.responses import FileResponse
import os

import core.config as core_config


def return_frontend_index(path: str):
    return FileResponse(core_config.FRONTEND_DIR + "/" + path)


def return_user_img_path(user_img: str):
    file_path = f"{core_config.USER_IMAGES_DIR}/" + user_img
    if not os.path.isfile(file_path):
        return None
    return FileResponse(file_path)


def return_server_img_path(server_img: str):
    file_path = f"{core_config.SERVER_IMAGES_DIR}/" + server_img
    if not os.path.isfile(file_path):
        return None
    return FileResponse(file_path)


def return_activity_media_path(media: str):
    file_path = f"{core_config.ACTIVITY_MEDIA_DIR}/" + media
    if not os.path.isfile(file_path):
        return None
    return FileResponse(file_path)
