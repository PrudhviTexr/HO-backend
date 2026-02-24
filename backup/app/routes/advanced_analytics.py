"""
Advanced Analytics Routes
Comprehensive analytics, trends, reports, and export functionality
"""
from fastapi import APIRouter, HTTPException, Depends, Query, Request
from typing import Optional, List, Dict, Any
from ..db.supabase_client import db
from ..core.security import get_current_user_claims, require_api_key
import datetime as dt
import traceback
import csv
import io

router = APIRouter()

@router.get("/analytics/trends")
async def get_trends(
    request: Request,
    time_range: str = Query("30d", description="Time range: 7d, 30d, 90d, 1y"),
    metric: str = Query("all", description="Metric: users, properties, bookings, inquiries, all")
):
    """Get trend data for analytics charts"""
    try:
        claims = get_current_user_claims(request)
        if not claims:
            raise HTTPException(status_code=401, detail="Not authenticated")
        
        user_type = None
        user_id = claims.get("sub")
        if user_id:
            user_data = await db.select("users", filters={"id": user_id})
            if user_data:
                user_type = user_data[0].get("user_type")
        
        # Parse time range
        range_map = {
            "7d": 7,
            "30d": 30,
            "90d": 90,
            "1y": 365
        }
        days = range_map.get(time_range, 30)
        
        end_date = dt.datetime.utcnow()
        start_date = end_date - dt.timedelta(days=days)
        
        # Get all data
        users_data = await db.admin_select("users") or []
        properties_data = await db.admin_select("properties") or []
        bookings_data = await db.admin_select("bookings") or []
        inquiries_data = await db.admin_select("inquiries") or []
        
        # Filter by date and create daily buckets
        daily_data = {}
        current = start_date
        while current <= end_date:
            date_key = current.strftime("%Y-%m-%d")
            daily_data[date_key] = {
                "date": date_key,
                "users": 0,
                "properties": 0,
                "bookings": 0,
                "inquiries": 0
            }
            current += dt.timedelta(days=1)
        
        # Count by date
        for user in users_data:
            created = user.get("created_at", "")
            if created:
                date_key = created[:10]  # YYYY-MM-DD
                if date_key in daily_data:
                    daily_data[date_key]["users"] += 1
        
        for prop in properties_data:
            created = prop.get("created_at", "")
            if created:
                date_key = created[:10]
                if date_key in daily_data:
                    daily_data[date_key]["properties"] += 1
        
        for booking in bookings_data:
            created = booking.get("created_at", "")
            if created:
                date_key = created[:10]
                if date_key in daily_data:
                    daily_data[date_key]["bookings"] += 1
        
        for inquiry in inquiries_data:
            created = inquiry.get("created_at", "")
            if created:
                date_key = created[:10]
                if date_key in daily_data:
                    daily_data[date_key]["inquiries"] += 1
        
        # Convert to list and filter based on metric
        trends = []
        for date_key in sorted(daily_data.keys()):
            day = daily_data[date_key]
            if metric == "all":
                trends.append(day)
            else:
                trends.append({
                    "date": day["date"],
                    metric: day[metric]
                })
        
        return {
            "success": True,
            "time_range": time_range,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "trends": trends
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ANALYTICS] Trends error: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to get trends: {str(e)}")

@router.get("/analytics/conversion-funnel")
async def get_conversion_funnel(
    request: Request,
    time_range: str = Query("30d"),
    _=Depends(require_api_key)
):
    """Get conversion funnel analytics"""
    try:
        # Parse time range
        range_map = {"7d": 7, "30d": 30, "90d": 90, "1y": 365}
        days = range_map.get(time_range, 30)
        
        end_date = dt.datetime.utcnow()
        start_date = end_date - dt.timedelta(days=days)
        start_str = start_date.isoformat()
        end_str = end_date.isoformat()
        
        # Get all properties, inquiries, bookings
        properties = await db.admin_select("properties") or []
        inquiries = await db.admin_select("inquiries") or []
        bookings = await db.admin_select("bookings") or []
        
        # Filter by date range
        properties_in_range = [
            p for p in properties
            if p.get("created_at", "") >= start_str and p.get("created_at", "") <= end_str
        ]
        inquiries_in_range = [
            i for i in inquiries
            if i.get("created_at", "") >= start_str and i.get("created_at", "") <= end_str
        ]
        bookings_in_range = [
            b for b in bookings
            if b.get("created_at", "") >= start_str and b.get("created_at", "") <= end_str
        ]
        
        # Calculate funnel
        property_ids = [p.get("id") for p in properties_in_range]
        inquiries_for_properties = [
            i for i in inquiries_in_range
            if i.get("property_id") in property_ids
        ]
        bookings_for_properties = [
            b for b in bookings_in_range
            if b.get("property_id") in property_ids
        ]
        
        total_properties = len(properties_in_range)
        total_inquiries = len(inquiries_for_properties)
        total_bookings = len(bookings_for_properties)
        
        conversion_rates = {
            "properties_to_inquiries": round((total_inquiries / max(total_properties, 1)) * 100, 2) if total_properties > 0 else 0,
            "inquiries_to_bookings": round((total_bookings / max(total_inquiries, 1)) * 100, 2) if total_inquiries > 0 else 0,
            "properties_to_bookings": round((total_bookings / max(total_properties, 1)) * 100, 2) if total_properties > 0 else 0
        }
        
        return {
            "success": True,
            "time_range": time_range,
            "funnel": {
                "properties": total_properties,
                "inquiries": total_inquiries,
                "bookings": total_bookings
            },
            "conversion_rates": conversion_rates
        }
        
    except Exception as e:
        print(f"[ANALYTICS] Conversion funnel error: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to get conversion funnel: {str(e)}")

@router.get("/analytics/revenue")
async def get_revenue_analytics(
    request: Request,
    time_range: str = Query("30d"),
    _=Depends(require_api_key)
):
    """Get revenue analytics"""
    try:
        range_map = {"7d": 7, "30d": 30, "90d": 90, "1y": 365}
        days = range_map.get(time_range, 30)
        
        end_date = dt.datetime.utcnow()
        start_date = end_date - dt.timedelta(days=days)
        start_str = start_date.isoformat()
        
        properties = await db.admin_select("properties") or []
        bookings = await db.admin_select("bookings") or []
        
        # Filter by date range
        properties_in_range = [
            p for p in properties
            if p.get("created_at", "") >= start_str
        ]
        bookings_in_range = [
            b for b in bookings
            if b.get("created_at", "") >= start_str
        ]
        
        # Calculate revenue metrics
        total_sale_value = sum(
            float(p.get("price", 0) or 0) for p in properties_in_range
            if p.get("listing_type") == "SALE"
        )
        
        total_rent_value = sum(
            float(p.get("monthly_rent", 0) or 0) for p in properties_in_range
            if p.get("listing_type") == "RENT"
        )
        
        # Calculate average prices
        sale_properties = [p for p in properties_in_range if p.get("listing_type") == "SALE"]
        rent_properties = [p for p in properties_in_range if p.get("listing_type") == "RENT"]
        
        avg_sale_price = total_sale_value / len(sale_properties) if sale_properties else 0
        avg_rent = total_rent_value / len(rent_properties) if rent_properties else 0
        
        return {
            "success": True,
            "time_range": time_range,
            "revenue": {
                "total_sale_value": total_sale_value,
                "total_rent_value": total_rent_value,
                "average_sale_price": avg_sale_price,
                "average_rent": avg_rent,
                "sale_properties_count": len(sale_properties),
                "rent_properties_count": len(rent_properties)
            },
            "bookings": len(bookings_in_range)
        }
        
    except Exception as e:
        print(f"[ANALYTICS] Revenue analytics error: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to get revenue analytics: {str(e)}")

@router.get("/analytics/export/csv")
async def export_analytics_csv(
    request: Request,
    report_type: str = Query(..., description="Type: users, properties, bookings, inquiries, all"),
    time_range: str = Query("all", description="Time range: 7d, 30d, 90d, 1y, all"),
    _=Depends(require_api_key)
):
    """Export analytics data as CSV"""
    try:
        range_map = {"7d": 7, "30d": 30, "90d": 90, "1y": 365}
        days = range_map.get(time_range, None)
        
        if days:
            end_date = dt.datetime.utcnow()
            start_date = end_date - dt.timedelta(days=days)
            start_str = start_date.isoformat()
        else:
            start_str = None
        
        # Prepare data based on report type
        output = io.StringIO()
        writer = csv.writer(output)
        
        if report_type in ["users", "all"]:
            users_data = await db.admin_select("users") or []
            if start_str:
                users_data = [u for u in users_data if u.get("created_at", "") >= start_str]
            
            writer.writerow(["User ID", "Email", "Name", "User Type", "Status", "Created At"])
            for user in users_data:
                writer.writerow([
                    user.get("id"),
                    user.get("email"),
                    f"{user.get('first_name', '')} {user.get('last_name', '')}".strip(),
                    user.get("user_type"),
                    user.get("status"),
                    user.get("created_at")
                ])
        
        if report_type in ["properties", "all"]:
            properties_data = await db.admin_select("properties") or []
            if start_str:
                properties_data = [p for p in properties_data if p.get("created_at", "") >= start_str]
            
            writer.writerow(["Property ID", "Title", "Type", "Price", "City", "Status", "Created At"])
            for prop in properties_data:
                writer.writerow([
                    prop.get("id"),
                    prop.get("title"),
                    prop.get("property_type"),
                    prop.get("price") or prop.get("monthly_rent"),
                    prop.get("city"),
                    prop.get("status"),
                    prop.get("created_at")
                ])
        
        if report_type in ["bookings", "all"]:
            bookings_data = await db.admin_select("bookings") or []
            if start_str:
                bookings_data = [b for b in bookings_data if b.get("created_at", "") >= start_str]
            
            writer.writerow(["Booking ID", "Property ID", "Buyer Email", "Status", "Date", "Created At"])
            for booking in bookings_data:
                writer.writerow([
                    booking.get("id"),
                    booking.get("property_id"),
                    booking.get("buyer_email"),
                    booking.get("status"),
                    booking.get("booking_date"),
                    booking.get("created_at")
                ])
        
        if report_type in ["inquiries", "all"]:
            inquiries_data = await db.admin_select("inquiries") or []
            if start_str:
                inquiries_data = [i for i in inquiries_data if i.get("created_at", "") >= start_str]
            
            writer.writerow(["Inquiry ID", "Property ID", "Buyer Email", "Status", "Created At"])
            for inquiry in inquiries_data:
                writer.writerow([
                    inquiry.get("id"),
                    inquiry.get("property_id"),
                    inquiry.get("buyer_email"),
                    inquiry.get("status"),
                    inquiry.get("created_at")
                ])
        
        csv_content = output.getvalue()
        output.close()
        
        return {
            "success": True,
            "content": csv_content,
            "content_type": "text/csv",
            "filename": f"analytics_{report_type}_{time_range}_{dt.datetime.utcnow().strftime('%Y%m%d')}.csv"
        }
        
    except Exception as e:
        print(f"[ANALYTICS] Export CSV error: {e}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to export CSV: {str(e)}")
