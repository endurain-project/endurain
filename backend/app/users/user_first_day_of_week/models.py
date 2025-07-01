
from typing import Optional


class User(SQLAlchemyBase):
    
    first_day_of_week: Optional[int] = Field(
        default=0, 
        ge=0, 
        le=6, 
        description="First day of week preference: 0=Sunday, 1=Monday, 2=Tuesday, 3=Wednesday, 4=Thursday, 5=Friday, 6=Saturday"
    )



class UserCreate(BaseModel):
    first_day_of_week: Optional[int] = Field(
        default=0, 
        ge=0, 
        le=6, 
        description="First day of week preference: 0=Sunday, 1=Monday, 2=Tuesday, 3=Wednesday, 4=Thursday, 5=Friday, 6=Saturday"
    )

class UserUpdate(BaseModel):
    first_day_of_week: Optional[int] = Field(
        None, 
        ge=0, 
        le=6, 
        description="First day of week preference: 0=Sunday, 1=Monday, 2=Tuesday, 3=Wednesday, 4=Thursday, 5=Friday, 6=Saturday"
    )

class UserRead(BaseModel):
    # ... existing fields ...
    first_day_of_week: Optional[int] = Field(
        default=0, 
        ge=0, 
        le=6, 
        description="First day of week preference: 0=Sunday, 1=Monday, 2=Tuesday, 3=Wednesday, 4=Thursday, 5=Friday, 6=Saturday"
    )