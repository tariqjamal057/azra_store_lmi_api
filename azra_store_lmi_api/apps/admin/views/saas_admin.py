"""SAAS Admin Management Module.

This module provides API endpoints for managing SAAS (Software as a Service) Administrators.
It includes functionality for listing, creating, retrieving, updating, and deleting SAAS
Admin accounts.

The module defines a FastAPI router with the following endpoints:
- GET /saas-admins: List all SAAS Admins with pagination and sorting
- POST /saas-admins: Create a new SAAS Admin
- GET /saas-admins/{saas_admin_id}: Retrieve details of a specific SAAS Admin
- PUT /saas-admins/{saas_admin_id}: Update an existing SAAS Admin
- DELETE /saas-admins/{saas_admin_id}: Delete a SAAS Admin

It uses SQLAlchemy for database operations and Pydantic for request/response modeling.
The module also includes comprehensive error handling and logging.
"""

# Rest of the file content follows...

from typing import Literal

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from fastapi_pagination import Page
from fastapi_pagination.ext.sqlalchemy import paginate
from sqlalchemy import and_, exists, select
from sqlalchemy import update as sqlalchemy_update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import load_only

from azra_store_lmi_api.apps.admin.models.saas_admin import SAASAdmin
from azra_store_lmi_api.apps.admin.schemas.saas_admin import ListSaaSAdmin, SAASAdminRequest
from azra_store_lmi_api.config.logger.app import logger
from azra_store_lmi_api.core.dependencies import get_db_session, paginator_query_params
from azra_store_lmi_api.core.exceptions import (
    CustomPydanticValidationError,
    HTTPNotFoundError,
    InternalServerErrorException,
)
from azra_store_lmi_api.core.utils import CustomParams, generate_password

saas_admin_router = APIRouter(
    prefix="/saas-admins",
    tags=["saas_admin"],
)

# Contains the list of sample response for all apis
RESPONSES = {
    "LIST": {
        status.HTTP_200_OK: {
            "description": "Successful response",
            "content": {
                "application/json": {
                    "example": {
                        "items": [
                            {
                                "id": 1,
                                "first_name": "User",
                                "last_name": "Name",
                                "email": "user@example.com",
                                "phone_number": "1234567890",
                                "is_active": True,
                                "created_at": "2024-11-19T16:14:12.815918+05:30",
                            }
                        ],
                        "total": 1,
                        "page": 1,
                        "size": 10,
                        "pages": 1,
                    }
                }
            },
        },
        status.HTTP_422_UNPROCESSABLE_ENTITY: {
            "description": "Validation error",
            "content": {
                "application/json": {
                    "examples": {
                        "Invalid value for sort_by & order_by": {
                            "summary": "Invalid value for sort_by & order_by",
                            "value": {
                                "detail": [
                                    {
                                        "type": "literal_error",
                                        "loc": ["query", "order_by"],
                                        "msg": "Input should be 'asc' or 'desc'",
                                        "input": "text",
                                        "ctx": {"expected": "'asc' or 'desc'"},
                                    },
                                    {
                                        "type": "literal_error",
                                        "loc": ["query", "sort_by"],
                                        "msg": "Input should be 'id' or 'email'",
                                        "input": "text",
                                        "ctx": {"expected": "'id' or 'email'"},
                                    },
                                ]
                            },
                        },
                        "Min Length Validation for page and size": {
                            "summary": "Min Length Validation for page and size",
                            "value": {
                                "detail": [
                                    {
                                        "type": "greater_than_equal",
                                        "loc": ["query", "page"],
                                        "msg": "Input should be greater than or equal to 1",
                                        "input": "0",
                                        "ctx": {"ge": 1},
                                    },
                                    {
                                        "type": "greater_than_equal",
                                        "loc": ["query", "size"],
                                        "msg": "Input should be greater than or equal to 1",
                                        "input": "0",
                                        "ctx": {"ge": 1},
                                    },
                                ]
                            },
                        },
                        "Max Length Validation for size": {
                            "summary": "Max Length Validation for size",
                            "value": {
                                "detail": [
                                    {
                                        "type": "less_than_equal",
                                        "loc": ["query", "size"],
                                        "msg": "Input should be less than or equal to 100",
                                        "input": "999",
                                        "ctx": {"le": 100},
                                    }
                                ]
                            },
                        },
                    }
                }
            },
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Internal server error",
            "content": {
                "application/json": {
                    "example": {"detail": "Unable to list SAAS Admins, please try again later."}
                }
            },
        },
    },
    "CREATE": {
        status.HTTP_201_CREATED: {
            "description": "SAAS Admin created successfully",
            "content": {
                "application/json": {
                    "example": {"detail": "SAAS Admin has been created successfully."}
                }
            },
        },
        status.HTTP_422_UNPROCESSABLE_ENTITY: {
            "description": "Validation error",
            "content": {
                "application/json": {
                    "examples": {
                        "SAAS Admin Exists": {
                            "summary": "Email already exists",
                            "value": {
                                "detail": [
                                    {
                                        "type": "value_error",
                                        "loc": ["body", "email"],
                                        "msg": "Value error, user@example.com SAAS Admin "
                                        "already exists",
                                        "input": "user@example.com",
                                        "ctx": {
                                            "error": "user@example.com SAAS Admin already exists."
                                        },
                                        "url": "https://errors.pydantic.dev/2.9/v/value_error",
                                    }
                                ]
                            },
                        },
                        "Invalid phone number length": {
                            "summary": "Invalid phone number length",
                            "value": {
                                "detail": [
                                    {
                                        "type": "value_error",
                                        "loc": ["body", "phone_number"],
                                        "msg": "Value error, Phone number must be exactly "
                                        "10 digits long",
                                        "input": "123456789",
                                        "ctx": {"error": {}},
                                    }
                                ]
                            },
                        },
                        "Invalid phone number and email": {
                            "summary": "Invalid phone number and email",
                            "value": {
                                "detail": [
                                    {
                                        "type": "value_error",
                                        "loc": ["body", "email"],
                                        "msg": "value is not a valid email address: An email "
                                        "address must have an @-sign.",
                                        "input": "userexamplecom",
                                        "ctx": {"reason": "An email address must have an @-sign."},
                                    },
                                    {
                                        "type": "value_error",
                                        "loc": ["body", "phone_number"],
                                        "msg": "Value error, Phone number must "
                                        "contain only digits",
                                        "input": "string",
                                        "ctx": {"error": {}},
                                    },
                                ]
                            },
                        },
                        "Minimum length validation": {
                            "summary": "Minimum length validation",
                            "value": {
                                "detail": [
                                    {
                                        "type": "string_too_short",
                                        "loc": ["body", "username"],
                                        "msg": "String should have at least 3 characters",
                                        "input": "a",
                                        "ctx": {"min_length": 3},
                                    },
                                    {
                                        "type": "string_too_short",
                                        "loc": ["body", "first_name"],
                                        "msg": "String should have at least 3 characters",
                                        "input": "a",
                                        "ctx": {"min_length": 3},
                                    },
                                    {
                                        "type": "string_too_short",
                                        "loc": ["body", "last_name"],
                                        "msg": "String should have at least 3 characters",
                                        "input": "a",
                                        "ctx": {"min_length": 3},
                                    },
                                ]
                            },
                        },
                        "Maximum length validation": {
                            "summary": "Maximum length validation",
                            "value": {
                                "detail": [
                                    {
                                        "type": "string_too_long",
                                        "loc": ["body", "username"],
                                        "msg": "String should have at most 50 characters",
                                        "input": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
                                        "aaaaaaaaaaaaaaaaaa",
                                        "ctx": {"max_length": 50},
                                    },
                                    {
                                        "type": "string_too_long",
                                        "loc": ["body", "first_name"],
                                        "msg": "String should have at most 50 characters",
                                        "input": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
                                        "aaaaaaaaaaaaaaaaa",
                                        "ctx": {"max_length": 50},
                                    },
                                    {
                                        "type": "string_too_long",
                                        "loc": ["body", "last_name"],
                                        "msg": "String should have at most 50 characters",
                                        "input": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
                                        "aaaaaaaaaaaaaaa",
                                        "ctx": {"max_length": 50},
                                    },
                                ]
                            },
                        },
                        "Invalid Value": {
                            "summary": "Invalid Value",
                            "value": {
                                "detail": [
                                    {
                                        "type": "string_type",
                                        "loc": ["body", "username"],
                                        "msg": "Input should be a valid string",
                                        "input": None,
                                    },
                                    {
                                        "type": "string_type",
                                        "loc": ["body", "first_name"],
                                        "msg": "Input should be a valid string",
                                        "input": None,
                                    },
                                    {
                                        "type": "string_type",
                                        "loc": ["body", "last_name"],
                                        "msg": "Input should be a valid string",
                                        "input": None,
                                    },
                                    {
                                        "type": "string_type",
                                        "loc": ["body", "email"],
                                        "msg": "Input should be a valid string",
                                        "input": None,
                                    },
                                    {
                                        "type": "string_type",
                                        "loc": ["body", "phone_number"],
                                        "msg": "Input should be a valid string",
                                        "input": None,
                                    },
                                ]
                            },
                        },
                        "Required Field Validation": {
                            "summary": "Required Field Validation",
                            "value": {
                                "detail": [
                                    {
                                        "type": "missing",
                                        "loc": ["body", "username"],
                                        "msg": "Field required",
                                        "input": {},
                                    },
                                    {
                                        "type": "missing",
                                        "loc": ["body", "first_name"],
                                        "msg": "Field required",
                                        "input": {},
                                    },
                                    {
                                        "type": "missing",
                                        "loc": ["body", "last_name"],
                                        "msg": "Field required",
                                        "input": {},
                                    },
                                    {
                                        "type": "missing",
                                        "loc": ["body", "email"],
                                        "msg": "Field required",
                                        "input": {},
                                    },
                                    {
                                        "type": "missing",
                                        "loc": ["body", "phone_number"],
                                        "msg": "Field required",
                                        "input": {},
                                    },
                                ]
                            },
                        },
                    }
                }
            },
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Internal server error",
            "content": {
                "application/json": {
                    "example": {"detail": "Unable to create SAAS Admin, please try again later."}
                }
            },
        },
    },
    "GET": {
        status.HTTP_200_OK: {
            "description": "Successful response",
            "content": {
                "application/json": {
                    "example": {
                        "id": 1,
                        "first_name": "John",
                        "last_name": "Doe",
                        "email": "john.doe@example.com",
                        "phone_number": "1234567890",
                        "is_active": True,
                        "created_at": "2024-11-19T16:14:12.815918+05:30",
                    }
                }
            },
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "SAAS Admin not found",
            "content": {"application/json": {"example": {"detail": "SAAS Admin not found."}}},
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Internal server error",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Unable to get details SAAS Admin, please try again later."
                    }
                }
            },
        },
    },
    "UPDATE": {
        status.HTTP_200_OK: {
            "description": "SAAS Admin updated successfully",
            "content": {
                "application/json": {
                    "example": {"detail": "John SAAS Admin has been updated successfully."}
                }
            },
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "SAAS Admin not found",
            "content": {"application/json": {"example": {"detail": "SAAS Admin not found."}}},
        },
        status.HTTP_422_UNPROCESSABLE_ENTITY: {
            "description": "Validation error",
            "content": {
                "application/json": {
                    "examples": {
                        "SAAS Admin Exists": {
                            "summary": "Email already exists",
                            "value": {
                                "detail": [
                                    {
                                        "type": "value_error",
                                        "loc": ["body", "email"],
                                        "msg": "Value error, user@example.com SAAS Admin "
                                        "already exists",
                                        "input": "user@example.com",
                                        "ctx": {
                                            "error": "user@example.com SAAS Admin already exists."
                                        },
                                        "url": "https://errors.pydantic.dev/2.9/v/value_error",
                                    }
                                ]
                            },
                        },
                        "Invalid phone number length": {
                            "summary": "Invalid phone number length",
                            "value": {
                                "detail": [
                                    {
                                        "type": "value_error",
                                        "loc": ["body", "phone_number"],
                                        "msg": "Value error, Phone number must be exactly "
                                        "10 digits long",
                                        "input": "123456789",
                                        "ctx": {"error": {}},
                                    }
                                ]
                            },
                        },
                        "Invalid phone number and email": {
                            "summary": "Invalid phone number and email",
                            "value": {
                                "detail": [
                                    {
                                        "type": "value_error",
                                        "loc": ["body", "email"],
                                        "msg": "value is not a valid email address: An email "
                                        "address must have an @-sign.",
                                        "input": "userexamplecom",
                                        "ctx": {"reason": "An email address must have an @-sign."},
                                    },
                                    {
                                        "type": "value_error",
                                        "loc": ["body", "phone_number"],
                                        "msg": "Value error, Phone number must contain "
                                        "only digits",
                                        "input": "string",
                                        "ctx": {"error": {}},
                                    },
                                ]
                            },
                        },
                        "Minimum length validation": {
                            "summary": "Minimum length validation",
                            "value": {
                                "detail": [
                                    {
                                        "type": "string_too_short",
                                        "loc": ["body", "username"],
                                        "msg": "String should have at least 3 characters",
                                        "input": "a",
                                        "ctx": {"min_length": 3},
                                    },
                                    {
                                        "type": "string_too_short",
                                        "loc": ["body", "first_name"],
                                        "msg": "String should have at least 3 characters",
                                        "input": "a",
                                        "ctx": {"min_length": 3},
                                    },
                                    {
                                        "type": "string_too_short",
                                        "loc": ["body", "last_name"],
                                        "msg": "String should have at least 3 characters",
                                        "input": "a",
                                        "ctx": {"min_length": 3},
                                    },
                                ]
                            },
                        },
                        "Maximum length validation": {
                            "summary": "Maximum length validation",
                            "value": {
                                "detail": [
                                    {
                                        "type": "string_too_long",
                                        "loc": ["body", "username"],
                                        "msg": "String should have at most 50 characters",
                                        "input": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
                                        "aaaaaaaaaaaaa",
                                        "ctx": {"max_length": 50},
                                    },
                                    {
                                        "type": "string_too_long",
                                        "loc": ["body", "first_name"],
                                        "msg": "String should have at most 50 characters",
                                        "input": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
                                        "aaaaaaaaaaaaa",
                                        "ctx": {"max_length": 50},
                                    },
                                    {
                                        "type": "string_too_long",
                                        "loc": ["body", "last_name"],
                                        "msg": "String should have at most 50 characters",
                                        "input": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
                                        "aaaaaaaaaaaaa",
                                        "ctx": {"max_length": 50},
                                    },
                                ]
                            },
                        },
                        "Invalid Value": {
                            "summary": "Invalid Value",
                            "value": {
                                "detail": [
                                    {
                                        "type": "string_type",
                                        "loc": ["body", "username"],
                                        "msg": "Input should be a valid string",
                                        "input": None,
                                    },
                                    {
                                        "type": "string_type",
                                        "loc": ["body", "first_name"],
                                        "msg": "Input should be a valid string",
                                        "input": None,
                                    },
                                    {
                                        "type": "string_type",
                                        "loc": ["body", "last_name"],
                                        "msg": "Input should be a valid string",
                                        "input": None,
                                    },
                                    {
                                        "type": "string_type",
                                        "loc": ["body", "email"],
                                        "msg": "Input should be a valid string",
                                        "input": None,
                                    },
                                    {
                                        "type": "string_type",
                                        "loc": ["body", "phone_number"],
                                        "msg": "Input should be a valid string",
                                        "input": None,
                                    },
                                ]
                            },
                        },
                        "Required Field Validation": {
                            "summary": "Required Field Validation",
                            "value": {
                                "detail": [
                                    {
                                        "type": "missing",
                                        "loc": ["body", "username"],
                                        "msg": "Field required",
                                        "input": {},
                                    },
                                    {
                                        "type": "missing",
                                        "loc": ["body", "first_name"],
                                        "msg": "Field required",
                                        "input": {},
                                    },
                                    {
                                        "type": "missing",
                                        "loc": ["body", "last_name"],
                                        "msg": "Field required",
                                        "input": {},
                                    },
                                    {
                                        "type": "missing",
                                        "loc": ["body", "email"],
                                        "msg": "Field required",
                                        "input": {},
                                    },
                                    {
                                        "type": "missing",
                                        "loc": ["body", "phone_number"],
                                        "msg": "Field required",
                                        "input": {},
                                    },
                                ]
                            },
                        },
                    }
                }
            },
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Internal server error",
            "content": {
                "application/json": {
                    "example": {"detail": "Unable to update SAAS Admin, please try again later."}
                }
            },
        },
    },
    "DELETE": {
        status.HTTP_200_OK: {
            "description": "SAAS Admin deleted successfully",
            "content": {
                "application/json": {
                    "example": {"detail": "john_doe SAAS Admin has been deleted successfully."}
                }
            },
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "SAAS Admin not found",
            "content": {"application/json": {"example": {"detail": "SAAS Admin not found."}}},
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Internal server error",
            "content": {
                "application/json": {
                    "example": {"detail": "Unable to delete SAAS Admin, please try again later."}
                }
            },
        },
    },
}


@saas_admin_router.get(
    "",
    response_model=Page[ListSaaSAdmin],
    name="List SAAS Admins",
    responses={
        status.HTTP_200_OK: RESPONSES["LIST"][status.HTTP_200_OK],
        status.HTTP_422_UNPROCESSABLE_ENTITY: RESPONSES["LIST"][
            status.HTTP_422_UNPROCESSABLE_ENTITY
        ],
        status.HTTP_500_INTERNAL_SERVER_ERROR: RESPONSES["LIST"][
            status.HTTP_500_INTERNAL_SERVER_ERROR
        ],
    },
)
async def list(
    request: Request,
    sort_by: Literal["id", "email"],
    paginator: dict = Depends(paginator_query_params),
    async_session: AsyncSession = Depends(get_db_session),
):
    """List SAAS Admins with pagination and sorting.

    This function retrieves a paginated list of SAAS Admins from the database,
    with optional sorting by id or email.

    Args:
        request (Request): The FastAPI request object.
        sort_by (Literal["id", "email"]): The field to sort the results by.
        paginator (dict): A dictionary containing pagination parameters.
            Obtained from the paginator_query_params dependency.
        async_session (AsyncSession): The asynchronous database session.

    Returns:
        Page: A Page object containing the paginated list of SAAS Admins.

    Raises:
        InternalServerErrorException: If an error occurs while retrieving the list.
    """
    try:
        query = (
            select(SAASAdmin)
            .options(
                load_only(
                    SAASAdmin.id,
                    SAASAdmin.first_name,
                    SAASAdmin.last_name,
                    SAASAdmin.email,
                    SAASAdmin.phone_number,
                    SAASAdmin.is_active,
                    SAASAdmin.created_at,
                )
            )
            .order_by(paginator["order_by"](sort_by))
        )

        return await paginate(
            async_session,
            query,
            params=CustomParams(page=paginator["page"], size=paginator["size"]),
        )
    except Exception as exception:
        logger.exception("Error occurred while listing saas admins: %s", exception)
        raise InternalServerErrorException(
            "Unable to list SAAS Admins, please try again later."
        ) from exception


@saas_admin_router.post(
    "",
    name="Create SAAS Admin",
    responses={
        status.HTTP_201_CREATED: RESPONSES["CREATE"][status.HTTP_201_CREATED],
        status.HTTP_422_UNPROCESSABLE_ENTITY: RESPONSES["CREATE"][
            status.HTTP_422_UNPROCESSABLE_ENTITY
        ],
        status.HTTP_500_INTERNAL_SERVER_ERROR: RESPONSES["CREATE"][
            status.HTTP_500_INTERNAL_SERVER_ERROR
        ],
    },
)
async def create(
    request: Request,
    saas_admin_request: SAASAdminRequest,
    async_session: AsyncSession = Depends(get_db_session),
):
    """Create a new SAAS Admin.

    This function creates a new SAAS Admin based on the provided request data.
    It checks if an admin with the given email already exists, and if not,
    creates a new admin with a generated password.

    Args:
        request (Request): The incoming request object.
        saas_admin_request (   SAASAdminRequest): The request model containing SAAS Admin details.
        async_session (AsyncSession): The database session for async operations.

    Returns:
        JSONResponse: A response indicating success or failure of the operation.

    Raises:
        CustomPydanticValidationError: If a SAAS Admin with the given email already exists.
        InternalServerErrorException: If an unexpected error occurs during the creation process.
    """
    try:
        saas_admin = await async_session.scalar(
            select(exists().where(SAASAdmin.email == saas_admin_request.email))
        )
        if saas_admin:
            raise IntegrityError(statement=None, params=None, orig=Exception())
        saas_admin_dict = saas_admin_request.model_dump() | {"password": generate_password()}
        saas_admin_data = SAASAdmin(**saas_admin_dict)
        async_session.add(saas_admin_data)
        await async_session.commit()
        await async_session.refresh(saas_admin_data)
        await saas_admin_data.send_admin_credential(saas_admin_dict["password"])
        return JSONResponse(
            {"detail": "SAAS Admin has been created successfully."},
            status_code=status.HTTP_201_CREATED,
        )
    except IntegrityError:
        return CustomPydanticValidationError(
            [
                {
                    "field": "email",
                    "message": f"{saas_admin_request.email} SAAS Admin already exists.",
                    "value": saas_admin_request.email,
                }
            ]
        )
    except Exception as exception:
        await async_session.rollback()
        logger.exception(
            "Error occurred while creating the sass admin!\n%s\nRequest Data:\n%s",
            exception,
            saas_admin_request.model_dump(),
        )
        raise InternalServerErrorException(
            "Unable to create SAAS Admin, please try again later."
        ) from exception


@saas_admin_router.get(
    "/{saas_admin_id}",
    name="Get SAAS Admin Details",
    responses={
        status.HTTP_200_OK: RESPONSES["GET"][status.HTTP_200_OK],
        status.HTTP_404_NOT_FOUND: RESPONSES["GET"][status.HTTP_404_NOT_FOUND],
        status.HTTP_500_INTERNAL_SERVER_ERROR: RESPONSES["GET"][
            status.HTTP_500_INTERNAL_SERVER_ERROR
        ],
    },
)
async def get(
    request: Request, saas_admin_id: int, async_session: AsyncSession = Depends(get_db_session)
):
    """Retrieve details of a specific SAAS Admin.

    This function fetches the details of a SAAS Admin based on the provided ID.
    It queries the database to retrieve specific fields of the SAAS Admin entity
    and returns them in a structured format.

    Args:
        request (Request): The incoming HTTP request object.
        saas_admin_id (int): The unique identifier of the SAAS Admin to retrieve.
        async_session (AsyncSession): The asynchronous database session,
        injected by FastAPI's dependency system.

    Returns:
        ListSaaSAdmin: An object containing the details of the requested SAAS Admin

    Raises:
        HTTPNotFoundError: If no SAAS Admin is found with the provided ID.
        InternalServerErrorException: If there's an unexpected error during the
        database query or data processing.

    Note:
        This function uses SQLAlchemy's select statement with load_only to optimize
        the database query by fetching only the required fields.
    """
    try:
        saas_admin = await async_session.scalar(
            select(SAASAdmin)
            .options(
                load_only(
                    SAASAdmin.id,
                    SAASAdmin.first_name,
                    SAASAdmin.last_name,
                    SAASAdmin.email,
                    SAASAdmin.phone_number,
                    SAASAdmin.is_active,
                    SAASAdmin.created_at,
                )
            )
            .where(SAASAdmin.id == saas_admin_id)
        )
        if not saas_admin:
            return HTTPNotFoundError("SAAS Admin not found.")
        return ListSaaSAdmin(**saas_admin.__dict__)
    except Exception as exception:
        logger.exception("Error Occurred while getting saas admin details: %s", exception)
        raise InternalServerErrorException(
            "Unable to get details SAAS Admin, please try again later."
        ) from exception


@saas_admin_router.put(
    "/{saas_admin_id}",
    name="Update SAAS Admin",
    responses={
        status.HTTP_200_OK: RESPONSES["UPDATE"][status.HTTP_200_OK],
        status.HTTP_404_NOT_FOUND: RESPONSES["UPDATE"][status.HTTP_404_NOT_FOUND],
        status.HTTP_422_UNPROCESSABLE_ENTITY: RESPONSES["UPDATE"][
            status.HTTP_422_UNPROCESSABLE_ENTITY
        ],
        status.HTTP_500_INTERNAL_SERVER_ERROR: RESPONSES["UPDATE"][
            status.HTTP_500_INTERNAL_SERVER_ERROR
        ],
    },
)
async def update(
    request: Request,
    saas_admin_id: int,
    saas_admin_request: SAASAdminRequest,
    async_session: AsyncSession = Depends(get_db_session),
):
    """Update a SAAS Admin's information.

    This function updates the information of a SAAS Admin based on the provided request data.
    It checks for the existence of the SAAS Admin, validates the uniqueness of the email,
    and updates the database with the new information.

    Args:
        request (Request): The incoming request object.
        saas_admin_id (int): The ID of the SAAS Admin to be updated.
        saas_admin_request (   SAASAdminRequest): The request object containing the
        updated SAAS Admin information.
        async_session (AsyncSession): The database session for executing database operations.

    Returns:
        JSONResponse: A JSON response indicating the success of the update operation.

    Raises:
        HTTPNotFoundError: If the SAAS Admin with the given ID is not found.
        CustomPydanticValidationError: If the provided email already exists for another SAAS Admin.
        InternalServerErrorException: If an unexpected error occurs during the update process.
    """
    try:
        saas_admin = await async_session.scalar(
            select(SAASAdmin)
            .options(load_only(SAASAdmin.id, SAASAdmin.username))
            .where(SAASAdmin.id == saas_admin_id)
        )
        if not saas_admin:
            return HTTPNotFoundError("SAAS Admin not found.")
        saas_admin_username = saas_admin.username

        if await async_session.scalar(
            select(
                exists().where(
                    and_(
                        SAASAdmin.email == saas_admin_request.email, SAASAdmin.id != saas_admin_id
                    )
                )
            )
        ):
            raise IntegrityError(statement=None, params=None, orig=Exception())

        await async_session.execute(
            sqlalchemy_update(SAASAdmin)
            .where(SAASAdmin.id == saas_admin_id)
            .values(**saas_admin_request.model_dump())
        )
        await async_session.commit()
        return JSONResponse(
            {"detail": f"{saas_admin_username} SAAS Admin has been updated successfully."},
            status_code=status.HTTP_200_OK,
        )
    except IntegrityError:
        return CustomPydanticValidationError(
            [
                {
                    "field": "email",
                    "message": f"{saas_admin_request.email} SAAS Admin already exists.",
                    "value": saas_admin_request.email,
                }
            ]
        )
    except Exception as exception:
        await async_session.rollback()
        logger.exception(
            "Error occurred while updating the saas admin!\n%s\nRequest Data:\n%s",
            exception,
            saas_admin_request.model_dump(),
        )
        raise InternalServerErrorException(
            "Unable to update SAAS Admin, please try again later."
        ) from exception


@saas_admin_router.delete(
    "/{saas_admin_id}",
    name="Delete SAAS Admin",
    responses={
        status.HTTP_200_OK: RESPONSES["DELETE"][status.HTTP_200_OK],
        status.HTTP_404_NOT_FOUND: RESPONSES["DELETE"][status.HTTP_404_NOT_FOUND],
        status.HTTP_500_INTERNAL_SERVER_ERROR: RESPONSES["DELETE"][
            status.HTTP_500_INTERNAL_SERVER_ERROR
        ],
    },
)
async def delete(
    request: Request, saas_admin_id: int, async_session: AsyncSession = Depends(get_db_session)
):
    """Delete a SAAS Admin.

    Args:
        request (Request): The incoming request object.
        saas_admin_id (int): The ID of the SAAS Admin to be deleted.
        async_session (AsyncSession): The database session.

    Returns:
        JSONResponse: A response indicating the success of the deletion.

    Raises:
        HTTPNotFoundError: If the SAAS Admin is not found.
        InternalServerErrorException: If there's an error during the deletion process.
    """
    try:
        saas_admin = await async_session.scalar(
            select(SAASAdmin)
            .options(load_only(SAASAdmin.id, SAASAdmin.username))
            .where(SAASAdmin.id == saas_admin_id)
        )
        if not saas_admin:
            return HTTPNotFoundError("SAAS Admin not found.")
        username = saas_admin.username
        saas_admin.delete()
        await async_session.commit()
        return JSONResponse(
            {"detail": f"{username} SAAS Admin has been deleted successfully."},
            status_code=status.HTTP_200_OK,
        )
    except Exception as exception:
        await async_session.rollback()
        logger.exception("Error Occurred while deleting saas admin: %s", exception)
        raise InternalServerErrorException(
            "Unable to delete SAAS Admin, please try again later."
        ) from exception
