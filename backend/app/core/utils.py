from fastapi.responses import FileResponse

def return_frontend_index(path: str):
    return FileResponse("/app/frontend/dist/" + path)


def return_user_img_path(user_img: str):
    return FileResponse("/app/backend/user_images/" + user_img)