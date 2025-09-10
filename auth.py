from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from database import get_db
from config import settings
import models, schemas

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT token scheme
security = HTTPBearer()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a hashed password."""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Hash a password."""
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Create a JWT access token with role and tenant claims."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)
    return encoded_jwt

def verify_token(token: str) -> Optional[Dict[str, Any]]:
    """Verify a JWT token and return the payload."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        return payload
    except jwt.PyJWTError:
        return None

def authenticate_user(db: Session, username: str, password: str) -> Optional[models.User]:
    """Authenticate a user by username/email and password."""
    # Try to find user by username or email
    user = db.query(models.User).filter(
        (models.User.username == username) | (models.User.email == username)
    ).first()
    
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> models.User:
    """Get the current authenticated user from JWT token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        token = credentials.credentials
        payload = verify_token(token)
        if payload is None:
            raise credentials_exception
        
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
            
    except jwt.PyJWTError:
        raise credentials_exception
    
    user = db.query(models.User).filter(models.User.username == username).first()
    if user is None:
        raise credentials_exception
    
    return user

def get_current_active_user(current_user: models.User = Depends(get_current_user)) -> models.User:
    """Get the current active user."""
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user

def get_current_admin_user(current_user: models.User = Depends(get_current_active_user)) -> models.User:
    """Get the current admin user."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user

def get_current_agency_user(current_user: models.User = Depends(get_current_active_user)) -> models.User:
    """Get the current agency user."""
    if current_user.role not in ["admin", "agency"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Agency access required"
        )
    return current_user

def create_user(db: Session, user: schemas.UserCreate) -> models.User:
    """Create a new user."""
    hashed_password = get_password_hash(user.password)
    db_user = models.User(
        email=user.email,
        username=user.username,
        hashed_password=hashed_password,
        role=user.role,
        first_name=user.first_name,
        last_name=user.last_name,
        phone=user.phone,
        avatar_url=user.avatar_url,
        is_active=user.is_active
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def get_user_agencies(db: Session, user: models.User) -> list[models.Agency]:
    """Get all agencies for a user."""
    if user.role == "admin":
        return db.query(models.Agency).filter(models.Agency.is_active == True).all()
    
    # Get agencies where user is a member
    agency_memberships = db.query(models.AgencyUser).filter(
        models.AgencyUser.user_id == user.id,
        models.AgencyUser.is_active == True
    ).all()
    
    agencies = []
    for membership in agency_memberships:
        if membership.agency.is_active:
            agencies.append(membership.agency)
    
    return agencies

def get_user_businesses(db: Session, user: models.User, agency_id: Optional[int] = None) -> list[models.Business]:
    """Get all businesses for a user, optionally filtered by agency."""
    if user.role == "admin":
        query = db.query(models.Business).filter(models.Business.is_active == True)
        if agency_id:
            query = query.filter(models.Business.agency_id == agency_id)
        return query.all()
    
    # Get businesses through agency memberships
    agencies = get_user_agencies(db, user)
    agency_ids = [agency.id for agency in agencies]
    
    if agency_id and agency_id not in agency_ids:
        return []  # User doesn't have access to this agency
    
    query = db.query(models.Business).filter(
        models.Business.agency_id.in_(agency_ids),
        models.Business.is_active == True
    )
    
    if agency_id:
        query = query.filter(models.Business.agency_id == agency_id)
    
    return query.all()

def verify_business_access(db: Session, user: models.User, business_id: int) -> bool:
    """Verify if user has access to a specific business."""
    if user.role == "admin":
        return True
    
    businesses = get_user_businesses(db, user)
    business_ids = [business.id for business in businesses]
    
    return business_id in business_ids

def verify_agency_access(db: Session, user: models.User, agency_id: int) -> bool:
    """Verify if user has access to a specific agency."""
    if user.role == "admin":
        return True
    
    agencies = get_user_agencies(db, user)
    agency_ids = [agency.id for agency in agencies]
    
    return agency_id in agency_ids

def get_user_role_in_agency(db: Session, user: models.User, agency_id: int) -> Optional[str]:
    """Get user's role in a specific agency."""
    if user.role == "admin":
        return "admin"
    
    membership = db.query(models.AgencyUser).filter(
        models.AgencyUser.user_id == user.id,
        models.AgencyUser.agency_id == agency_id,
        models.AgencyUser.is_active == True
    ).first()
    
    return membership.role if membership else None

def get_user_role_in_business(db: Session, user: models.User, business_id: int) -> Optional[str]:
    """Get user's role in a specific business."""
    if user.role == "admin":
        return "admin"
    
    # Check direct business membership
    membership = db.query(models.BusinessUser).filter(
        models.BusinessUser.user_id == user.id,
        models.BusinessUser.business_id == business_id,
        models.BusinessUser.is_active == True
    ).first()
    
    if membership:
        return membership.role
    
    # Check agency access to business
    business = db.query(models.Business).filter(models.Business.id == business_id).first()
    if business:
        agency_role = get_user_role_in_agency(db, user, business.agency_id)
        if agency_role:
            return agency_role
    
    return None

def require_business_access(
    business_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
) -> models.Business:
    """Dependency to require access to a specific business."""
    if not verify_business_access(db, current_user, business_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to this business is not allowed"
        )
    
    business = db.query(models.Business).filter(models.Business.id == business_id).first()
    if not business:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business not found"
        )
    
    return business

def require_agency_access(
    agency_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
) -> models.Agency:
    """Dependency to require access to a specific agency."""
    if not verify_agency_access(db, current_user, agency_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access to this agency is not allowed"
        )
    
    agency = db.query(models.Agency).filter(models.Agency.id == agency_id).first()
    if not agency:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agency not found"
        )
    
    return agency

def create_login_token(user: models.User, agency_id: Optional[int] = None, business_id: Optional[int] = None) -> str:
    """Create a login token with user context."""
    token_data = {
        "sub": user.username,
        "role": user.role,
        "user_id": user.id
    }
    
    if agency_id:
        token_data["agency_id"] = agency_id
    
    if business_id:
        token_data["business_id"] = business_id
    
    return create_access_token(data=token_data)