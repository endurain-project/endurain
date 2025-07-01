
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.users.models import User
from app.users.user_first_day_of_week.models import (
    UserFirstDayOfWeekCreate,
    UserFirstDayOfWeekRead,
    UserFirstDayOfWeekUpdate
)
from app.users.user_first_day_of_week.crud import (
    get_user_first_day_of_week,
    update_user_first_day_of_week,
    create_or_update_user_first_day_of_week
)

router = APIRouter()


@router.get(
    "/users/{user_id}/first-day-of-week", 
    response_model=UserFirstDayOfWeekRead,
    status_code=status.HTTP_200_OK,
    summary="Get user's first day of week preference",
    description="Retrieve the user's preferred first day of the week (0=Sunday, 1=Monday, etc.)"
)
def get_user_first_day_of_week_route(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Get user's first day of week preference
    """
    # Check if the current user can access this user's data
    if current_user.user_id != user_id and current_user.access_type != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions to access this user's preferences"
        )
    
    first_day_of_week = get_user_first_day_of_week(db, user_id)
    
    if not first_day_of_week:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return first_day_of_week


@router.put(
    "/users/{user_id}/first-day-of-week",
    response_model=UserFirstDayOfWeekRead,
    status_code=status.HTTP_200_OK,
    summary="Update user's first day of week preference",
    description="Update the user's preferred first day of the week (0=Sunday, 1=Monday, etc.)"
)
def update_user_first_day_of_week_route(
    user_id: int,
    first_day_of_week_data: UserFirstDayOfWeekUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Update user's first day of week preference
    """
    # Check if the current user can modify this user's data
    if current_user.user_id != user_id and current_user.access_type != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions to modify this user's preferences"
        )
    
    try:
        updated_first_day_of_week = update_user_first_day_of_week(db, user_id, first_day_of_week_data)
        
        if not updated_first_day_of_week:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        return updated_first_day_of_week
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post(
    "/users/{user_id}/first-day-of-week",
    response_model=UserFirstDayOfWeekRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create or update user's first day of week preference",
    description="Create or update the user's preferred first day of the week (0=Sunday, 1=Monday, etc.)"
)
def create_user_first_day_of_week_route(
    user_id: int,
    first_day_of_week_data: UserFirstDayOfWeekCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Any:
    """
    Create or update user's first day of week preference
    """
    if current_user.user_id != user_id and current_user.access_type != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions to modify this user's preferences"
        )
    
    try:
        first_day_of_week = create_or_update_user_first_day_of_week(db, user_id, first_day_of_week_data)
        return first_day_of_week
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )