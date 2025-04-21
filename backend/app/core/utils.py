from fastapi.responses import FileResponse
import os


def return_frontend_index(path: str):
    return FileResponse("/app/frontend/dist/" + path)


def return_user_img_path(user_img: str):
    file_path = "/app/backend/user_images/" + user_img
    if not os.path.isfile(file_path):
        return None
    return FileResponse(file_path)


def return_server_img_path(server_img: str):
    file_path = "/app/backend/server_images/" + server_img
    if not os.path.isfile(file_path):
        return None
    return FileResponse(file_path)
