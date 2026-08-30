"""
Router for Template Analytics with Manual CR Override functionality.

This router provides endpoints for:
1. Viewing template-specific performance analytics
2. Manually adjusting conversion rates and counts for specific templates on specific dates
3. Tracking template performance across campaigns and direct links
"""
from fastapi import APIRouter, Depends, Query, HTTPException
from typing import Optional, List
from datetime import datetime, timedelta
from app.models.template_analytics import TemplateAnalytics, ManualCRUpdateRequest, TemplatePerformance
from app.dependencies import get_db, get_current_admin, get_current_user
from app.core.exceptions import NotFoundError
from bson import ObjectId
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/template-analytics", tags=["Template Analytics"])


@router.get("/templates/{template_id}/daily", response_model=List[TemplateAnalytics])
async def get_template_daily_analytics(
    template_id: str,
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD format"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD format"),
    current_user: dict = Depends(get_current_admin),
    db = Depends(get_db),
):
    """Get daily analytics for a specific template with optional date range."""
    try:
        # Validate template exists
        template = await db.prelander_templates.find_one({"_id": ObjectId(template_id)})
        if not template:
            raise NotFoundError("Prelander Template")

        query = {"template_id": template_id}
        
        # Add date range filter if provided
        if date_from or date_to:
            date_filter = {}
            if date_from:
                date_filter["$gte"] = date_from
            if date_to:
                date_filter["$lte"] = date_to
            query["date"] = date_filter

        cursor = db.template_analytics.find(query).sort("date", -1)
        analytics = await cursor.to_list(length=None)
        
        # Convert ObjectId to string
        for item in analytics:
            item["id"] = str(item.pop("_id", ""))
            if item.get("override_updated_at"):
                item["override_updated_at"] = item["override_updated_at"].isoformat()
            if item.get("created_at"):
                item["created_at"] = item["created_at"].isoformat()
            if item.get("updated_at"):
                item["updated_at"] = item["updated_at"].isoformat()
        
        return analytics
    
    except Exception as e:
        logger.error(f"Error fetching template analytics: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch template analytics")


@router.post("/templates/{template_id}/manual-cr")
async def update_manual_conversion_rate(
    template_id: str,
    data: ManualCRUpdateRequest,
    current_user: dict = Depends(get_current_admin),
    db = Depends(get_db),
):
    """Manually override conversion rate/count for a template on a specific date."""
    try:
        # Validate template exists
        template = await db.prelander_templates.find_one({"_id": ObjectId(template_id)})
        if not template:
            raise NotFoundError("Prelander Template")

        # Ensure template_id matches URL parameter
        if data.template_id != template_id:
            raise HTTPException(status_code=400, detail="Template ID mismatch")

        # Find or create analytics record for this date
        analytics_query = {"template_id": template_id, "date": data.date}
        existing = await db.template_analytics.find_one(analytics_query)
        
        now = datetime.utcnow()
        update_data = {
            "manual_cr_override": data.manual_cr,
            "manual_conversions_override": data.manual_conversions,
            "override_reason": data.reason,
            "override_updated_at": now,
            "override_updated_by": current_user.get("id"),
            "updated_at": now,
        }

        if existing:
            # Update existing record
            await db.template_analytics.update_one(
                {"_id": existing["_id"]},
                {"$set": update_data}
            )
        else:
            # Create new analytics record with manual override
            new_record = {
                "template_id": template_id,
                "date": data.date,
                "total_clicks": 0,
                "unique_clicks": 0,
                "valid_clicks": 0,
                "invalid_clicks": 0,
                "fraud_clicks": 0,
                "total_conversions": 0,
                "conversion_rate": 0.0,
                "geo_stats": {},
                "device_stats": {},
                "created_at": now,
                **update_data
            }
            await db.template_analytics.insert_one(new_record)

        return {
            "success": True,
            "message": f"Manual CR override applied for {data.date}",
            "applied_values": {
                "manual_cr": data.manual_cr,
                "manual_conversions": data.manual_conversions,
                "reason": data.reason,
            }
        }
    
    except Exception as e:
        logger.error(f"Error updating manual CR: {e}")
        raise HTTPException(status_code=500, detail="Failed to update manual conversion rate")


@router.get("/templates/{template_id}/performance", response_model=TemplatePerformance)
async def get_template_performance_summary(
    template_id: str,
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    current_user: dict = Depends(get_current_admin),
    db = Depends(get_db),
):
    """Get performance summary for a template over specified period."""
    try:
        # Validate template exists and get name
        template = await db.prelander_templates.find_one({"_id": ObjectId(template_id)})
        if not template:
            raise NotFoundError("Prelander Template")

        # Calculate date range
        end_date = datetime.utcnow().strftime("%Y-%m-%d")
        start_date = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")

        # Aggregate analytics data
        pipeline = [
            {
                "$match": {
                    "template_id": template_id,
                    "date": {"$gte": start_date, "$lte": end_date}
                }
            },
            {
                "$group": {
                    "_id": None,
                    "total_clicks": {"$sum": "$total_clicks"},
                    "total_conversions": {"$sum": "$total_conversions"},
                    "dates": {"$push": {"date": "$date", "conversions": "$total_conversions", "clicks": "$total_clicks"}}
                }
            }
        ]

        result = await db.template_analytics.aggregate(pipeline).to_list(length=1)
        
        if not result:
            return TemplatePerformance(
                template_id=template_id,
                template_name=template.get("name", "Unknown"),
                total_clicks=0,
                total_conversions=0,
                average_cr=0.0
            )

        data = result[0]
        total_clicks = data.get("total_clicks", 0)
        total_conversions = data.get("total_conversions", 0)
        average_cr = (total_conversions / total_clicks * 100) if total_clicks > 0 else 0.0

        # Find best/worst performing dates
        dates_data = data.get("dates", [])
        best_date = None
        worst_date = None
        
        if dates_data:
            # Sort by conversion rate
            for d in dates_data:
                d["cr"] = (d["conversions"] / d["clicks"] * 100) if d["clicks"] > 0 else 0
            
            dates_data.sort(key=lambda x: x["cr"], reverse=True)
            best_date = dates_data[0]["date"] if dates_data[0]["cr"] > 0 else None
            worst_date = dates_data[-1]["date"] if len(dates_data) > 1 else None

        # Simple trend calculation (last 7 days vs previous 7 days)
        trend = "stable"
        if len(dates_data) >= 14:
            recent_avg = sum(d["cr"] for d in dates_data[:7]) / 7
            previous_avg = sum(d["cr"] for d in dates_data[7:14]) / 7
            if recent_avg > previous_avg * 1.1:
                trend = "up"
            elif recent_avg < previous_avg * 0.9:
                trend = "down"

        return TemplatePerformance(
            template_id=template_id,
            template_name=template.get("name", "Unknown"),
            total_clicks=total_clicks,
            total_conversions=total_conversions,
            average_cr=round(average_cr, 2),
            best_performing_date=best_date,
            worst_performing_date=worst_date,
            trend_direction=trend
        )
    
    except Exception as e:
        logger.error(f"Error getting template performance: {e}")
        raise HTTPException(status_code=500, detail="Failed to get template performance")


@router.get("/overview")
async def get_templates_overview(
    current_user: dict = Depends(get_current_admin),
    db = Depends(get_db),
):
    """Get overview of all template performances."""
    try:
        # Get all active templates
        templates_cursor = db.prelander_templates.find({"status": "active"})
        templates = await templates_cursor.to_list(length=None)
        
        overview_data = []
        
        for template in templates:
            template_id = str(template["_id"])
            
            # Get analytics for last 30 days
            end_date = datetime.utcnow().strftime("%Y-%m-%d")
            start_date = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d")
            
            pipeline = [
                {
                    "$match": {
                        "template_id": template_id,
                        "date": {"$gte": start_date, "$lte": end_date}
                    }
                },
                {
                    "$group": {
                        "_id": None,
                        "total_clicks": {"$sum": "$total_clicks"},
                        "total_conversions": {"$sum": "$total_conversions"}
                    }
                }
            ]

            result = await db.template_analytics.aggregate(pipeline).to_list(length=1)
            data = result[0] if result else {"total_clicks": 0, "total_conversions": 0}
            
            cr = (data["total_conversions"] / data["total_clicks"] * 100) if data["total_clicks"] > 0 else 0.0
            
            overview_data.append({
                "template_id": template_id,
                "template_name": template.get("name", ""),
                "template_status": template.get("status", ""),
                "os_type": template.get("os_type", "both"),
                "total_clicks_30d": data["total_clicks"],
                "total_conversions_30d": data["total_conversions"],
                "conversion_rate_30d": round(cr, 2),
            })
        
        # Sort by conversion rate descending
        overview_data.sort(key=lambda x: x["conversion_rate_30d"], reverse=True)
        
        return {
            "success": True,
            "templates": overview_data,
            "total_templates": len(overview_data),
            "date_range": f"{start_date} to {end_date}"
        }
    
    except Exception as e:
        logger.error(f"Error getting templates overview: {e}")
        raise HTTPException(status_code=500, detail="Failed to get templates overview")


@router.delete("/templates/{template_id}/manual-cr")
async def remove_manual_cr_override(
    template_id: str,
    date: str = Query(..., description="Date in YYYY-MM-DD format"),
    current_user: dict = Depends(get_current_admin),
    db = Depends(get_db),
):
    """Remove manual CR override for a specific date, reverting to automatic calculation."""
    try:
        # Find analytics record
        analytics = await db.template_analytics.find_one({
            "template_id": template_id,
            "date": date
        })
        
        if not analytics:
            raise NotFoundError("Analytics record not found for this date")
        
        # Remove manual overrides
        update_data = {
            "$unset": {
                "manual_cr_override": "",
                "manual_conversions_override": "",
                "override_reason": "",
                "override_updated_at": "",
                "override_updated_by": ""
            },
            "$set": {"updated_at": datetime.utcnow()}
        }
        
        await db.template_analytics.update_one(
            {"_id": analytics["_id"]},
            update_data
        )
        
        return {
            "success": True,
            "message": f"Manual CR override removed for {date}"
        }
    
    except Exception as e:
        logger.error(f"Error removing manual CR override: {e}")
        raise HTTPException(status_code=500, detail="Failed to remove manual CR override")