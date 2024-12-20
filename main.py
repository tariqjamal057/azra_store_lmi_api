from fastapi import FastAPI
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi

from azra_store_lmi_api.apps.admin.routes import admin_app

app = FastAPI(
    title="AZRA Store LMI API",
    summary="A SaaS laundry management system for single and multi-store businesses, "
    "facilitating bill generation, updates, customer assignment, and cash payment logging. "
    "Customers can view and pay bills through multiple channels and receive status reminders. "
    "It includes dashboards, transaction reporting, and high-value alerts for efficient and "
    "secure operations.",
    description="This SaaS-based laundry management solution supports both single-location and "
    "multi-store setups, streamlining billing and payment processes. It enables businesses to "
    "generate, update, and assign bills, log cash payments, and provide reminders on order "
    "status. Customers benefit from convenient bill viewing and payment options, including "
    "UPI, wallets and cards. Robust features such as customizable dashboards, detailed "
    "transaction reports, and alerts for high-value orders ensure secure handling and "
    "improved operational oversight for businesses and customers alike.",
    version="1.0.0",
    docs_url=None,  # Disable default Swagger UI
    redoc_url=None,  # Disable ReDoc
    openapi_url=None,  # Disable default OpenAPI JSON endpoint
)


@app.get("/health-check")
async def health_check():
    """Endpoint to check the health status of the application.

    Returns:
        dict: A dictionary containing the status of the application.
    """
    return {"status": True}


# Custom OpenAPI generation
@app.get("/openapi.json", include_in_schema=False)
async def custom_openapi():
    """Generate a custom OpenAPI schema by combining the main app schema with the admin app schema.

    This function creates a combined OpenAPI schema by merging the main application's
    schema with the admin application's schema. It updates the paths and components
    of the main schema with those from the admin schema.

    Returns:
        dict: The combined OpenAPI schema containing paths and components from both
              the main and admin applications.
    """
    main_schema = get_openapi(
        title=app.title,
        summary=app.summary,
        description=app.description,
        version="1.0.0",
        routes=app.routes,
    )
    sub_schema = admin_app.openapi()
    main_schema["paths"].update(sub_schema.get("paths", {}))
    main_schema["components"] = main_schema.get("components", {})
    main_schema["components"].update(sub_schema.get("components", {}))

    return main_schema


@app.get("/docs", include_in_schema=False)
async def custom_docs():
    """Generate custom Swagger UI documentation.

    This function creates and returns the HTML content for the Swagger UI
    documentation. It uses the custom OpenAPI schema generated by the
    '/openapi.json' endpoint.

    Returns:
        HTMLResponse: The HTML content for the Swagger UI documentation.
    """
    return get_swagger_ui_html(openapi_url="/openapi.json", title="AZRA Store LMI API Docs")


# Mount the admin app at root
app.mount("", admin_app)
