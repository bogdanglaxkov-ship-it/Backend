from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


def register_validation_exception_handler(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        errors: dict[str, str] = {}
        for err in exc.errors():
            # err["loc"] looks like ("body", "email") — drop the "body" prefix
            field = ".".join(str(p) for p in err["loc"][1:]) or "form"
            if field not in errors:
                errors[field] = err["msg"]

        return JSONResponse(
            status_code=422,
            content={
                "success": False,
                "message": "Проверьте правильность заполнения полей",
                "errors": errors,
            },
        )


# В main.py подключите так:
#   from utils.error_handlers import register_validation_exception_handler
#   app = FastAPI()
#   register_validation_exception_handler(app)
