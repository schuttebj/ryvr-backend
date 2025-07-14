from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import List
from datetime import datetime, timedelta

from ..database import get_db
from ..auth import get_current_active_user
from .. import models, schemas

router = APIRouter()

@router.get("/dashboard", response_model=schemas.DashboardStats)
async def get_dashboard_stats(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get main dashboard statistics."""
    # Total clients
    total_clients = db.query(models.Client).filter(
        models.Client.owner_id == current_user.id,
        models.Client.is_active == True
    ).count()
    
    # Active workflows
    active_workflows = db.query(models.Workflow).join(models.Client).filter(
        models.Client.owner_id == current_user.id,
        models.Workflow.is_active == True
    ).count()
    
    # Total credits used
    total_credits_used = db.query(func.sum(models.Client.credits_used)).filter(
        models.Client.owner_id == current_user.id
    ).scalar() or 0
    
    # Recent executions (last 30 days)
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    recent_executions = db.query(models.WorkflowExecution).join(
        models.Workflow
    ).join(models.Client).filter(
        models.Client.owner_id == current_user.id,
        models.WorkflowExecution.started_at >= thirty_days_ago
    ).count()
    
    return schemas.DashboardStats(
        total_clients=total_clients,
        active_workflows=active_workflows,
        total_credits_used=total_credits_used,
        recent_executions=recent_executions
    )

@router.get("/clients/{client_id}/stats", response_model=schemas.ClientStats)
async def get_client_stats(
    client_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get statistics for a specific client."""
    # Verify client ownership
    client = db.query(models.Client).filter(
        models.Client.id == client_id,
        models.Client.owner_id == current_user.id
    ).first()
    if client is None:
        raise HTTPException(status_code=404, detail="Client not found")
    
    # Active workflows for this client
    active_workflows = db.query(models.Workflow).filter(
        models.Workflow.client_id == client_id,
        models.Workflow.is_active == True
    ).count()
    
    # Total executions
    total_executions = db.query(models.WorkflowExecution).join(
        models.Workflow
    ).filter(
        models.Workflow.client_id == client_id
    ).count()
    
    # Success rate
    successful_executions = db.query(models.WorkflowExecution).join(
        models.Workflow
    ).filter(
        models.Workflow.client_id == client_id,
        models.WorkflowExecution.status == "completed"
    ).count()
    
    success_rate = (successful_executions / total_executions * 100) if total_executions > 0 else 0
    
    return schemas.ClientStats(
        client_id=client_id,
        credits_balance=client.credits_balance,
        credits_used=client.credits_used,
        active_workflows=active_workflows,
        total_executions=total_executions,
        success_rate=success_rate
    )

@router.get("/executions/recent")
async def get_recent_executions(
    limit: int = 10,
    client_id: int = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get recent workflow executions."""
    query = db.query(models.WorkflowExecution).join(
        models.Workflow
    ).join(models.Client).filter(
        models.Client.owner_id == current_user.id
    )
    
    if client_id:
        query = query.filter(models.Workflow.client_id == client_id)
    
    executions = query.order_by(
        desc(models.WorkflowExecution.started_at)
    ).limit(limit).all()
    
    return executions

@router.get("/usage/credits")
async def get_credit_usage(
    days: int = 30,
    client_id: int = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get credit usage over time."""
    start_date = datetime.utcnow() - timedelta(days=days)
    
    query = db.query(models.CreditTransaction).join(
        models.Client
    ).filter(
        models.Client.owner_id == current_user.id,
        models.CreditTransaction.created_at >= start_date
    )
    
    if client_id:
        query = query.filter(models.CreditTransaction.client_id == client_id)
    
    transactions = query.order_by(models.CreditTransaction.created_at).all()
    
    # Group by date
    usage_by_date = {}
    for transaction in transactions:
        date_key = transaction.created_at.date().isoformat()
        if date_key not in usage_by_date:
            usage_by_date[date_key] = {"purchases": 0, "usage": 0, "net": 0}
        
        if transaction.transaction_type == "usage":
            usage_by_date[date_key]["usage"] += abs(transaction.amount)
        elif transaction.transaction_type in ["purchase", "adjustment"]:
            usage_by_date[date_key]["purchases"] += transaction.amount
        
        usage_by_date[date_key]["net"] += transaction.amount
    
    return {
        "period_days": days,
        "usage_by_date": usage_by_date,
        "total_transactions": len(transactions)
    }

@router.get("/performance/workflows")
async def get_workflow_performance(
    client_id: int = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """Get workflow performance metrics."""
    query = db.query(
        models.Workflow.id,
        models.Workflow.name,
        func.count(models.WorkflowExecution.id).label("total_executions"),
        func.sum(
            func.case(
                (models.WorkflowExecution.status == "completed", 1),
                else_=0
            )
        ).label("successful_executions"),
        func.avg(models.WorkflowExecution.credits_used).label("avg_credits"),
        func.sum(models.WorkflowExecution.credits_used).label("total_credits")
    ).join(models.Client).outerjoin(
        models.WorkflowExecution
    ).filter(
        models.Client.owner_id == current_user.id
    ).group_by(models.Workflow.id, models.Workflow.name)
    
    if client_id:
        query = query.filter(models.Workflow.client_id == client_id)
    
    results = query.all()
    
    performance_data = []
    for result in results:
        success_rate = (
            (result.successful_executions / result.total_executions * 100)
            if result.total_executions > 0 else 0
        )
        
        performance_data.append({
            "workflow_id": result.id,
            "workflow_name": result.name,
            "total_executions": result.total_executions,
            "successful_executions": result.successful_executions,
            "success_rate": success_rate,
            "avg_credits": float(result.avg_credits or 0),
            "total_credits": result.total_credits or 0
        })
    
    return {
        "workflows": performance_data,
        "total_workflows": len(performance_data)
    } 