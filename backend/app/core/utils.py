from fastapi.responses import RedirectResponse

def return_frontend_index():
    return RedirectResponse(url="/index.html")