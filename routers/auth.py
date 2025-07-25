from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta
from typing import List

from database import get_db, engine, Base
from auth import (
    authenticate_user, 
    create_access_token, 
    get_current_active_user, 
    get_current_admin_user,
    create_user,
    get_password_hash
)
from config import settings
import models, schemas

router = APIRouter()

@router.post("/login", response_model=schemas.Token)
async def login_for_access_token(
    form_data: schemas.LoginRequest,
    db: Session = Depends(get_db)
):
    """Login endpoint to get access token."""
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/register", response_model=schemas.User)
async def register_user(
    user: schemas.UserCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user)
):
    """Register a new user (admin only)."""
    # Check if username already exists
    db_user = db.query(models.User).filter(
        (models.User.username == user.username) | (models.User.email == user.email)
    ).first()
    if db_user:
        raise HTTPException(
            status_code=400,
            detail="Username or email already registered"
        )
    
    return create_user(db=db, user=user)

@router.get("/me", response_model=schemas.User)
async def read_users_me(current_user: models.User = Depends(get_current_active_user)):
    """Get current user information."""
    return current_user

@router.get("/users", response_model=List[schemas.User])
async def read_users(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user)
):
    """Get all users (admin only)."""
    users = db.query(models.User).offset(skip).limit(limit).all()
    return users

@router.put("/users/{user_id}", response_model=schemas.User)
async def update_user(
    user_id: int,
    user_update: schemas.UserUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user)
):
    """Update a user (admin only)."""
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found")
    
    for field, value in user_update.dict(exclude_unset=True).items():
        setattr(db_user, field, value)
    
    db.commit()
    db.refresh(db_user)
    return db_user

@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_admin_user)
):
    """Delete a user (admin only)."""
    if user_id == current_user.id:
        raise HTTPException(
            status_code=400, 
            detail="Cannot delete your own account"
        )
    
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found")
    
    db.delete(db_user)
    db.commit()
    return {"message": "User deleted successfully"}

@router.post("/reset-database")
async def reset_database(
    db: Session = Depends(get_db)
):
    """Reset database and create default admin user (development only)."""
    try:
        # Drop all tables
        Base.metadata.drop_all(bind=engine)
        
        # Create all tables
        Base.metadata.create_all(bind=engine)
        
        # Create default admin user
        admin_user = models.User(
            email="admin@ryvr.com",
            username="admin",
            hashed_password=get_password_hash("password"),
            full_name="Admin User",
            is_active=True,
            is_admin=True
        )
        
        db.add(admin_user)
        db.commit()
        
        return {
            "message": "Database reset successfully",
            "admin_credentials": {
                "email": "admin@ryvr.com", 
                "username": "admin",
                "password": "password"
            }
        }
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reset database: {str(e)}"
        )

@router.post("/init-database")
async def init_database(
    db: Session = Depends(get_db)
):
    """Initialize database with default admin user (development only)."""
    try:
        # Check if admin user already exists
        existing_admin = db.query(models.User).filter(
            (models.User.email == "admin@ryvr.com") | (models.User.username == "admin")
        ).first()
        
        if existing_admin:
            return {
                "message": "Admin user already exists",
                "admin_credentials": {
                    "email": "admin@ryvr.com", 
                    "username": "admin",
                    "password": "password"
                }
            }
        
        # Create default admin user
        admin_user = models.User(
            email="admin@ryvr.com",
            username="admin",
            hashed_password=get_password_hash("password"),
            full_name="Admin User",
            is_active=True,
            is_admin=True
        )
        
        db.add(admin_user)
        db.commit()
        
        return {
            "message": "Admin user created successfully",
            "admin_credentials": {
                "email": "admin@ryvr.com", 
                "username": "admin",
                "password": "password"
            }
        }
        
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to initialize database: {str(e)}"
        ) 