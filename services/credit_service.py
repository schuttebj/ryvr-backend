"""
Credit System Service
Handles credit management, transactions, and billing for the multi-tenant platform
"""

import logging
from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from decimal import Decimal

import models

logger = logging.getLogger(__name__)

class CreditService:
    """Service for managing credit pools, transactions, and billing"""
    
    def __init__(self, db: Session):
        self.db = db
    
    # =============================================================================
    # CREDIT POOL MANAGEMENT
    # =============================================================================
    
    def get_credit_pool(self, user_id: int) -> Optional[models.CreditPool]:
        """Get credit pool for user"""
        return self.db.query(models.CreditPool).filter(
            models.CreditPool.owner_id == user_id
        ).first()
    
    def create_credit_pool(
        self, 
        user_id: int, 
        initial_balance: int = 0,
        overage_threshold: int = 100
    ) -> models.CreditPool:
        """Create a new credit pool for a user"""
        pool = models.CreditPool(
            owner_id=user_id,
            balance=initial_balance,
            total_purchased=initial_balance if initial_balance > 0 else 0,
            overage_threshold=overage_threshold
        )
        
        self.db.add(pool)
        self.db.commit()
        self.db.refresh(pool)
        
        # Log initial transaction if there's a balance
        if initial_balance > 0:
            self.add_credits(
                pool.id,
                initial_balance,
                "Initial credit allocation",
                transaction_type="purchase"
            )
        
        return pool
    
    def ensure_credit_pool(self, user_id: int) -> models.CreditPool:
        """Ensure credit pool exists for user, create if not"""
        pool = self.get_credit_pool(user_id)
        if not pool:
            pool = self.create_credit_pool(user_id)
        return pool
    
    # =============================================================================
    # CREDIT TRANSACTIONS
    # =============================================================================
    
    def add_credits(
        self,
        pool_id: int,
        amount: int,
        description: str,
        transaction_type: str = "purchase",
        business_id: Optional[int] = None,
        workflow_execution_id: Optional[int] = None,
        created_by: Optional[int] = None
    ) -> models.CreditTransaction:
        """Add credits to a pool"""
        pool = self.db.query(models.CreditPool).filter(
            models.CreditPool.id == pool_id
        ).first()
        
        if not pool:
            raise Exception("Credit pool not found")
        
        # Update pool balance
        pool.balance += amount
        if transaction_type == "purchase":
            pool.total_purchased += amount
        
        # Create transaction record
        transaction = models.CreditTransaction(
            pool_id=pool_id,
            business_id=business_id,
            workflow_execution_id=workflow_execution_id,
            transaction_type=transaction_type,
            amount=amount,
            balance_after=pool.balance,
            description=description,
            created_by=created_by
        )
        
        self.db.add(transaction)
        self.db.commit()
        self.db.refresh(transaction)
        
        logger.info(f"Added {amount} credits to pool {pool_id}. New balance: {pool.balance}")
        
        return transaction
    
    def deduct_credits(
        self,
        pool_id: int,
        amount: int,
        description: str,
        business_id: Optional[int] = None,
        workflow_execution_id: Optional[int] = None,
        created_by: Optional[int] = None,
        allow_overage: bool = True
    ) -> models.CreditTransaction:
        """Deduct credits from a pool"""
        pool = self.db.query(models.CreditPool).filter(
            models.CreditPool.id == pool_id
        ).first()
        
        if not pool:
            raise Exception("Credit pool not found")
        
        # Check if deduction is allowed
        new_balance = pool.balance - amount
        
        if new_balance < 0 and not allow_overage:
            raise Exception("Insufficient credits")
        
        if new_balance < -pool.overage_threshold:
            raise Exception(f"Credit limit exceeded. Maximum overage: {pool.overage_threshold}")
        
        # Update pool balance
        pool.balance = new_balance
        pool.total_used += amount
        
        # Suspend pool if over threshold
        if new_balance < -pool.overage_threshold:
            pool.is_suspended = True
        
        # Create transaction record
        transaction = models.CreditTransaction(
            pool_id=pool_id,
            business_id=business_id,
            workflow_execution_id=workflow_execution_id,
            transaction_type="usage",
            amount=-amount,  # Negative for deductions
            balance_after=pool.balance,
            description=description,
            created_by=created_by
        )
        
        self.db.add(transaction)
        self.db.commit()
        self.db.refresh(transaction)
        
        logger.info(f"Deducted {amount} credits from pool {pool_id}. New balance: {pool.balance}")
        
        return transaction
    
    def check_credit_availability(
        self,
        pool_id: int,
        required_credits: int
    ) -> Dict[str, Any]:
        """Check if enough credits are available"""
        pool = self.db.query(models.CreditPool).filter(
            models.CreditPool.id == pool_id
        ).first()
        
        if not pool:
            return {
                "available": False,
                "error": "Credit pool not found"
            }
        
        if pool.is_suspended:
            return {
                "available": False,
                "error": "Credit pool is suspended",
                "balance": pool.balance,
                "required": required_credits
            }
        
        # Check if credits are available (including overage)
        available_credits = pool.balance + pool.overage_threshold
        
        if available_credits >= required_credits:
            return {
                "available": True,
                "balance": pool.balance,
                "required": required_credits,
                "after_deduction": pool.balance - required_credits
            }
        else:
            return {
                "available": False,
                "error": "Insufficient credits (including overage)",
                "balance": pool.balance,
                "required": required_credits,
                "available_with_overage": available_credits
            }
    
    # =============================================================================
    # BUSINESS CREDIT OPERATIONS
    # =============================================================================
    
    def get_business_credit_pool(self, business_id: int) -> Optional[models.CreditPool]:
        """Get credit pool for a business (through its owner user)"""
        business = self.db.query(models.Business).filter(
            models.Business.id == business_id
        ).first()
        
        if not business:
            return None
        
        return self.get_credit_pool(business.owner_id)
    
    def deduct_business_credits(
        self,
        business_id: int,
        amount: int,
        description: str,
        workflow_execution_id: Optional[int] = None,
        created_by: Optional[int] = None
    ) -> models.CreditTransaction:
        """Deduct credits for a business operation"""
        business = self.db.query(models.Business).filter(
            models.Business.id == business_id
        ).first()
        
        if not business:
            raise Exception("Business not found")
        
        # Get user credit pool
        pool = self.get_credit_pool(business.owner_id)
        if not pool:
            raise Exception("No credit pool found for business owner")
        
        return self.deduct_credits(
            pool_id=pool.id,
            amount=amount,
            description=description,
            business_id=business_id,
            workflow_execution_id=workflow_execution_id,
            created_by=created_by
        )
    
    def check_business_credits(
        self,
        business_id: int,
        required_credits: int
    ) -> bool:
        """Check if business can use required credits (returns boolean for simple usage)"""
        business = self.db.query(models.Business).filter(
            models.Business.id == business_id
        ).first()
        
        if not business:
            return False
        
        pool = self.get_credit_pool(business.owner_id)
        if not pool:
            return False
        
        result = self.check_credit_availability(pool.id, required_credits)
        return result.get("available", False)
    
    # =============================================================================
    # CREDIT ANALYTICS
    # =============================================================================
    
    def get_credit_usage_stats(
        self,
        pool_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Get credit usage statistics for a pool"""
        pool = self.db.query(models.CreditPool).filter(
            models.CreditPool.id == pool_id
        ).first()
        
        if not pool:
            return {"error": "Credit pool not found"}
        
        # Set default date range (last 30 days)
        if not start_date:
            start_date = datetime.utcnow() - timedelta(days=30)
        if not end_date:
            end_date = datetime.utcnow()
        
        # Get transactions in date range
        transactions = self.db.query(models.CreditTransaction).filter(
            models.CreditTransaction.pool_id == pool_id,
            models.CreditTransaction.created_at >= start_date,
            models.CreditTransaction.created_at <= end_date
        ).all()
        
        # Calculate statistics
        total_purchased = sum(t.amount for t in transactions if t.transaction_type == "purchase")
        total_used = sum(abs(t.amount) for t in transactions if t.transaction_type == "usage")
        total_refunded = sum(t.amount for t in transactions if t.transaction_type == "refund")
        
        # Usage by business
        business_usage = {}
        for t in transactions:
            if t.business_id and t.transaction_type == "usage":
                if t.business_id not in business_usage:
                    business_usage[t.business_id] = 0
                business_usage[t.business_id] += abs(t.amount)
        
        return {
            "pool_id": pool_id,
            "current_balance": pool.balance,
            "total_purchased_all_time": pool.total_purchased,
            "total_used_all_time": pool.total_used,
            "period_stats": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "purchased": total_purchased,
                "used": total_used,
                "refunded": total_refunded,
                "net_change": total_purchased + total_refunded - total_used
            },
            "business_usage": business_usage,
            "transaction_count": len(transactions)
        }
    
    def get_user_credit_breakdown(self, user_id: int) -> Dict[str, Any]:
        """Get detailed credit breakdown for a user"""
        pool = self.get_credit_pool(user_id)
        if not pool:
            return {"error": "Credit pool not found for user"}
        
        # Get all businesses for this user
        businesses = self.db.query(models.Business).filter(
            models.Business.owner_id == user_id,
            models.Business.is_active == True
        ).all()
        
        # Get credit usage per business
        business_breakdown = []
        total_business_usage = 0
        
        for business in businesses:
            business_transactions = self.db.query(models.CreditTransaction).filter(
                models.CreditTransaction.pool_id == pool.id,
                models.CreditTransaction.business_id == business.id,
                models.CreditTransaction.transaction_type == "usage"
            ).all()
            
            business_usage = sum(abs(t.amount) for t in business_transactions)
            total_business_usage += business_usage
            
            business_breakdown.append({
                "business_id": business.id,
                "business_name": business.name,
                "credits_used": business_usage,
                "last_usage": max([t.created_at for t in business_transactions]) if business_transactions else None
            })
        
        return {
            "user_id": user_id,
            "pool": {
                "balance": pool.balance,
                "total_purchased": pool.total_purchased,
                "total_used": pool.total_used,
                "overage_threshold": pool.overage_threshold,
                "is_suspended": pool.is_suspended
            },
            "business_count": len(businesses),
            "total_business_usage": total_business_usage,
            "business_breakdown": business_breakdown
        }
    
    # =============================================================================
    # CREDIT PACKAGES & PRICING
    # =============================================================================
    
    def calculate_credit_cost(self, credits: int, tier_slug: str = "professional") -> Dict[str, Any]:
        """Calculate cost for purchasing credits"""
        # Base pricing: $10 for 1000 credits
        base_rate = 0.01  # $0.01 per credit
        
        # Tier discounts
        tier_discounts = {
            "starter": 1.0,      # No discount
            "professional": 0.9,  # 10% discount
            "enterprise": 0.8     # 20% discount
        }
        
        discount_rate = tier_discounts.get(tier_slug, 1.0)
        
        # Volume discounts
        if credits >= 100000:
            volume_discount = 0.8  # Additional 20% for 100k+
        elif credits >= 50000:
            volume_discount = 0.9  # Additional 10% for 50k+
        elif credits >= 10000:
            volume_discount = 0.95  # Additional 5% for 10k+
        else:
            volume_discount = 1.0
        
        # Calculate final cost
        base_cost = credits * base_rate
        tier_cost = base_cost * discount_rate
        final_cost = tier_cost * volume_discount
        
        return {
            "credits": credits,
            "base_cost": round(base_cost, 2),
            "tier_discount": round((1 - discount_rate) * 100, 1),
            "volume_discount": round((1 - volume_discount) * 100, 1),
            "final_cost": round(final_cost, 2),
            "cost_per_credit": round(final_cost / credits, 4),
            "savings": round(base_cost - final_cost, 2)
        }
    
    def purchase_credits(
        self,
        user_id: int,
        credits: int,
        payment_method: str,
        payment_reference: str,
        tier_slug: str = "professional",
        created_by: Optional[int] = None
    ) -> Dict[str, Any]:
        """Process credit purchase for a user"""
        try:
            # Calculate cost
            cost_info = self.calculate_credit_cost(credits, tier_slug)
            
            # Get or create credit pool
            pool = self.ensure_credit_pool(user_id)
            
            # Add credits
            transaction = self.add_credits(
                pool_id=pool.id,
                amount=credits,
                description=f"Credit purchase - {credits:,} credits for ${cost_info['final_cost']}",
                transaction_type="purchase",
                created_by=created_by
            )
            
            # Log payment details (in a real system, this would integrate with Stripe)
            logger.info(f"Credit purchase completed: {credits} credits for ${cost_info['final_cost']} - {payment_reference}")
            
            return {
                "success": True,
                "transaction_id": transaction.id,
                "credits_purchased": credits,
                "cost": cost_info['final_cost'],
                "new_balance": pool.balance,
                "payment_reference": payment_reference
            }
            
        except Exception as e:
            logger.error(f"Credit purchase failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }
