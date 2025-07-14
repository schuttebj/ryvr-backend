from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from ..database import get_db
from ..auth import get_current_active_user
from .. import models, schemas

router = APIRouter()

@router.get("/", response_model=List[schemas.Client])
async def read_clients(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get all clients for the current user."""
    clients = db.query(models.Client).filter(
        models.Client.owner_id == current_user.id
    ).offset(skip).limit(limit).all()
    return clients

@router.post("/", response_model=schemas.Client)
async def create_client(
    client: schemas.ClientCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Create a new client."""
    db_client = models.Client(
        **client.dict(),
        owner_id=current_user.id
    )
    db.add(db_client)
    db.commit()
    db.refresh(db_client)
    
    # Create initial credit transaction
    credit_transaction = models.CreditTransaction(
        client_id=db_client.id,
        transaction_type="purchase",
        amount=client.credits_balance,
        description="Initial credit allocation"
    )
    db.add(credit_transaction)
    db.commit()
    
    return db_client

@router.get("/{client_id}", response_model=schemas.Client)
async def read_client(
    client_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get a specific client."""
    client = db.query(models.Client).filter(
        models.Client.id == client_id,
        models.Client.owner_id == current_user.id
    ).first()
    if client is None:
        raise HTTPException(status_code=404, detail="Client not found")
    return client

@router.put("/{client_id}", response_model=schemas.Client)
async def update_client(
    client_id: int,
    client_update: schemas.ClientUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Update a client."""
    db_client = db.query(models.Client).filter(
        models.Client.id == client_id,
        models.Client.owner_id == current_user.id
    ).first()
    if db_client is None:
        raise HTTPException(status_code=404, detail="Client not found")
    
    # Handle credit balance changes
    old_balance = db_client.credits_balance
    
    for field, value in client_update.dict(exclude_unset=True).items():
        setattr(db_client, field, value)
    
    # If credits balance changed, create transaction
    if hasattr(client_update, 'credits_balance') and client_update.credits_balance is not None:
        if client_update.credits_balance != old_balance:
            difference = client_update.credits_balance - old_balance
            credit_transaction = models.CreditTransaction(
                client_id=client_id,
                transaction_type="purchase" if difference > 0 else "adjustment",
                amount=difference,
                description=f"Credit balance adjustment from {old_balance} to {client_update.credits_balance}"
            )
            db.add(credit_transaction)
    
    db.commit()
    db.refresh(db_client)
    return db_client

@router.delete("/{client_id}")
async def delete_client(
    client_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Delete a client."""
    db_client = db.query(models.Client).filter(
        models.Client.id == client_id,
        models.Client.owner_id == current_user.id
    ).first()
    if db_client is None:
        raise HTTPException(status_code=404, detail="Client not found")
    
    db.delete(db_client)
    db.commit()
    return {"message": "Client deleted successfully"}

# Website management for clients
@router.get("/{client_id}/websites", response_model=List[schemas.Website])
async def read_client_websites(
    client_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get all websites for a client."""
    # Verify client ownership
    client = db.query(models.Client).filter(
        models.Client.id == client_id,
        models.Client.owner_id == current_user.id
    ).first()
    if client is None:
        raise HTTPException(status_code=404, detail="Client not found")
    
    websites = db.query(models.Website).filter(
        models.Website.client_id == client_id
    ).all()
    return websites

@router.post("/{client_id}/websites", response_model=schemas.Website)
async def create_website(
    client_id: int,
    website: schemas.WebsiteCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Create a new website for a client."""
    # Verify client ownership
    client = db.query(models.Client).filter(
        models.Client.id == client_id,
        models.Client.owner_id == current_user.id
    ).first()
    if client is None:
        raise HTTPException(status_code=404, detail="Client not found")
    
    # Override client_id from URL
    website_data = website.dict()
    website_data['client_id'] = client_id
    
    db_website = models.Website(**website_data)
    db.add(db_website)
    db.commit()
    db.refresh(db_website)
    return db_website

@router.get("/{client_id}/credits", response_model=List[schemas.CreditTransaction])
async def read_client_credit_transactions(
    client_id: int,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get credit transaction history for a client."""
    # Verify client ownership
    client = db.query(models.Client).filter(
        models.Client.id == client_id,
        models.Client.owner_id == current_user.id
    ).first()
    if client is None:
        raise HTTPException(status_code=404, detail="Client not found")
    
    transactions = db.query(models.CreditTransaction).filter(
        models.CreditTransaction.client_id == client_id
    ).order_by(models.CreditTransaction.created_at.desc()).offset(skip).limit(limit).all()
    return transactions

@router.post("/{client_id}/credits", response_model=schemas.CreditTransaction)
async def add_credits(
    client_id: int,
    credit_data: schemas.CreditTransactionCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Add credits to a client account."""
    # Verify client ownership
    client = db.query(models.Client).filter(
        models.Client.id == client_id,
        models.Client.owner_id == current_user.id
    ).first()
    if client is None:
        raise HTTPException(status_code=404, detail="Client not found")
    
    # Override client_id from URL
    credit_data.client_id = client_id
    
    # Create transaction
    transaction = models.CreditTransaction(**credit_data.dict())
    db.add(transaction)
    
    # Update client balance
    client.credits_balance += credit_data.amount
    
    db.commit()
    db.refresh(transaction)
    return transaction 