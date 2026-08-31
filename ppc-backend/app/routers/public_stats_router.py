from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional
from datetime import datetime, timedelta
import base64

from app.dependencies import get_db


router = APIRouter(prefix="/public-stats", tags=["Public Stats"])


@router.get("/{publisher_id}")
async def get_publisher_stats(
    publisher_id: str,
    token: str = Query(...),
    db = Depends(get_db)
):
    """Get white-label publisher statistics (no authentication required)"""
    
    try:
        # Basic token validation - decode and verify format
        decoded_token = base64.b64decode(token).decode('utf-8')
        if ':' not in decoded_token:
            raise HTTPException(status_code=403, detail="Invalid access token")
        
        token_pub_id, timestamp = decoded_token.split(':', 1)
        
        # Verify publisher ID matches token
        if token_pub_id != publisher_id:
            raise HTTPException(status_code=403, detail="Token mismatch")
        
    except Exception:
        raise HTTPException(status_code=403, detail="Invalid access token")
    
    # Check if publisher exists
    from bson import ObjectId
    try:
        object_id = ObjectId(publisher_id)
    except:
        raise HTTPException(status_code=404, detail="Publisher not found")
    
    publisher = await db.publishers.find_one({
        "_id": object_id,
        "role": "publisher"
    })
    
    if not publisher:
        raise HTTPException(status_code=404, detail="Publisher not found")
    
    # Calculate date range (last 30 days)
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=30)
    
    # Get click statistics
    click_pipeline = [
        {
            "$match": {
                "publisher_id": publisher_id,
                "created_at": {"$gte": start_date, "$lte": end_date},
                "is_fraud": False
            }
        },
        {
            "$group": {
                "_id": None,
                "total_clicks": {"$sum": 1},
                "windows_clicks": {
                    "$sum": {
                        "$cond": [{"$eq": ["$os", "Windows"]}, 1, 0]
                    }
                },
                "mac_clicks": {
                    "$sum": {
                        "$cond": [{"$eq": ["$os", "macOS"]}, 1, 0]
                    }
                }
            }
        }
    ]
    
    click_stats = await db.clicks.aggregate(click_pipeline).to_list(length=1)
    click_data = click_stats[0] if click_stats else {
        "total_clicks": 0,
        "windows_clicks": 0,
        "mac_clicks": 0
    }
    
    # Get daily breakdown
    daily_pipeline = [
        {
            "$match": {
                "publisher_id": publisher_id,
                "created_at": {"$gte": start_date, "$lte": end_date},
                "is_fraud": False
            }
        },
        {
            "$group": {
                "_id": {
                    "$dateToString": {
                        "format": "%Y-%m-%d",
                        "date": "$created_at"
                    }
                },
                "clicks": {"$sum": 1},
                "windows_clicks": {
                    "$sum": {
                        "$cond": [{"$eq": ["$os", "Windows"]}, 1, 0]
                    }
                },
                "mac_clicks": {
                    "$sum": {
                        "$cond": [{"$eq": ["$os", "macOS"]}, 1, 0]
                    }
                }
            }
        },
        {"$sort": {"_id": -1}},
        {"$limit": 30}
    ]
    
    daily_clicks = await db.clicks.aggregate(daily_pipeline).to_list(length=30)
    
    # Get conversion data (from direct_link_conversions or similar)
    conversion_pipeline = [
        {
            "$match": {
                "publisher_id": publisher_id,
                "created_at": {"$gte": start_date, "$lte": end_date}
            }
        },
        {
            "$group": {
                "_id": None,
                "total_conversions": {"$sum": 1}
            }
        }
    ]
    
    # Try to get conversions from direct link conversions collection
    conversion_stats = []
    try:
        collections = await db.list_collection_names()
        if "direct_link_conversions" in collections:
            conversion_stats = await db.direct_link_conversions.aggregate(conversion_pipeline).to_list(length=1)
    except Exception:
        # Fallback if collection doesn't exist
        pass
    
    total_conversions = conversion_stats[0]["total_conversions"] if conversion_stats else 0
    
    # Calculate conversion rate
    conversion_rate = (total_conversions / click_data["total_clicks"] * 100) if click_data["total_clicks"] > 0 else 0
    
    # Build daily breakdown with conversion data
    daily_breakdown = []
    for day_data in daily_clicks:
        date = day_data["_id"]
        clicks = day_data["clicks"]
        
        # Get conversions for this day (mock for now - replace with real query)
        daily_conversions = max(0, int(clicks * (conversion_rate / 100) * (0.8 + 0.4 * hash(date) % 100 / 100)))
        daily_cr = (daily_conversions / clicks * 100) if clicks > 0 else 0
        
        daily_breakdown.append({
            "date": date,
            "clicks": clicks,
            "conversions": daily_conversions,
            "cr": round(daily_cr, 2),
            "windows_clicks": day_data["windows_clicks"],
            "mac_clicks": day_data["mac_clicks"]
        })
    
    # Calculate insights
    avg_daily_clicks = click_data["total_clicks"] / 30
    windows_ratio = click_data["windows_clicks"] / click_data["total_clicks"] if click_data["total_clicks"] > 0 else 0
    
    # Determine performance score
    if conversion_rate >= 6:
        performance_score = "Excellent"
    elif conversion_rate >= 4:
        performance_score = "Good"
    elif conversion_rate >= 2:
        performance_score = "Average"
    else:
        performance_score = "Needs Improvement"
    
    # Determine trend (compare recent vs older data)
    if len(daily_breakdown) >= 14:
        recent_avg = sum(day["clicks"] for day in daily_breakdown[:7]) / 7
        older_avg = sum(day["clicks"] for day in daily_breakdown[7:14]) / 7
        
        if recent_avg > older_avg * 1.1:
            trend = "up"
        elif recent_avg < older_avg * 0.9:
            trend = "down"
        else:
            trend = "stable"
    else:
        trend = "stable"
    
    # Determine platform preference
    if windows_ratio > 0.65:
        platform_preference = "windows"
    elif windows_ratio < 0.35:
        platform_preference = "mac"
    else:
        platform_preference = "balanced"
    
    # Find top performance day
    top_day = max(daily_breakdown, key=lambda x: x["cr"]) if daily_breakdown else None
    
    return {
        "success": True,
        "data": {
            "publisher_name": publisher.get("name", "Publisher"),
            "publisher_id": publisher_id,
            "date_range": "Last 30 Days",
            "total_impressions": click_data["total_clicks"],
            "unique_windows_clicks": click_data["windows_clicks"],
            "unique_mac_clicks": click_data["mac_clicks"],
            "total_conversions": total_conversions,
            "conversion_rate": round(conversion_rate, 2),
            "performance_score": performance_score,
            "daily_breakdown": daily_breakdown,
            "insights": {
                "top_performance_day": top_day["date"] if top_day else None,
                "avg_daily_clicks": round(avg_daily_clicks),
                "trend_direction": trend,
                "platform_preference": platform_preference
            }
        }
    }