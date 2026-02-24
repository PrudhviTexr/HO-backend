from fastapi import APIRouter, HTTPException, Depends, Request
from starlette.requests import Request
from ..models.schemas import InquiryRequest, BookingRequest, PropertyRequest, BookingUpdateRequest, InquiryUpdateRequest
from ..core.security import require_api_key
from ..services.email import send_email
from ..services.templates import inquiry_email, booking_email, booking_status_email, inquiry_status_email, notify_info
from ..db.supabase_client import db
import datetime as dt
import uuid

router = APIRouter()


@router.post("/contact")
async def create_contact_message(data: dict):
    """Handle contact form submissions from website"""
    try:
        print(f"[RECORDS] Received contact form submission")
        
        name = data.get("name", "")
        email = data.get("email", "")
        message = data.get("message", "")
        form_type = data.get("form_type", "general")  # general, property_management, consultation
        
        if not name or not email or not message:
            raise HTTPException(status_code=400, detail="Name, email, and message are required")
        
        # Store in database (optional - create contacts table if needed)
        contact_data = {
            "id": str(uuid.uuid4()),
            "name": name,
            "email": email,
            "message": message,
            "form_type": form_type,
            "status": "new",
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat()
        }
        
        # Try to save to database (if table exists)
        try:
            await db.insert("contacts", contact_data)
            print(f"[RECORDS] Contact saved to database")
        except Exception as db_error:
            print(f"[RECORDS] Database save failed (table may not exist): {db_error}")
            # Continue anyway - email is more important
        
        # Send email to admin
        admin_html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 10px;">
                <h2 style="color: #2563eb; border-bottom: 2px solid #2563eb; padding-bottom: 10px;">
                    New Contact Form Submission
                </h2>
                
                <div style="margin: 20px 0; padding: 15px; background-color: #f9fafb; border-radius: 5px;">
                    <p><strong style="color: #162e5a;">Form Type:</strong> {form_type.replace('_', ' ').title()}</p>
                    <p><strong style="color: #162e5a;">Name:</strong> {name}</p>
                    <p><strong style="color: #162e5a;">Email:</strong> {email}</p>
                </div>
                
                <div style="margin: 20px 0; padding: 15px; background-color: #fff; border: 1px solid #e5e7eb; border-radius: 5px;">
                    <h3 style="color: #162e5a; margin-top: 0;">Message:</h3>
                    <p style="white-space: pre-wrap;">{message}</p>
                </div>
                
                <div style="margin-top: 20px; padding: 15px; background-color: #fef3c7; border-left: 4px solid #f59e0b; border-radius: 5px;">
                    <p style="margin: 0;"><strong>Action Required:</strong> Please respond to this inquiry at your earliest convenience.</p>
                </div>
                
                <hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">
                <p style="color: #999; font-size: 12px; text-align: center;">
                    © 2025 Home & Own. All rights reserved.
                </p>
            </div>
        </body>
        </html>
        """
        
        email_result_admin = await send_email(
            to="info@homeandown.com",
            subject=f"New Contact Form Submission from {name}",
            html=admin_html
        )
        if email_result_admin.get("status") == "sent":
            print(f"[RECORDS] ✅ Contact form email sent to admin via {email_result_admin.get('provider', 'unknown')}")
        else:
            print(f"[RECORDS] ⚠️ Contact form email to admin may have failed: {email_result_admin.get('error', 'Unknown error')}")
        
        # Send confirmation email to user
        user_html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 10px;">
                <div style="text-align: center; margin-bottom: 20px;">
                    <h2 style="color: #2563eb; margin: 0;">Thank You for Contacting Us!</h2>
                </div>
                
                <p>Hello {name},</p>
                
                <p>We have received your message and appreciate you reaching out to Home & Own.</p>
                
                <div style="margin: 20px 0; padding: 15px; background-color: #f0f9ff; border-left: 4px solid #2563eb; border-radius: 5px;">
                    <p style="margin: 0;"><strong>Your message:</strong></p>
                    <p style="margin: 10px 0 0 0; white-space: pre-wrap;">{message}</p>
                </div>
                
                <p>Our team will review your inquiry and get back to you within 24-48 hours.</p>
                
                <p>In the meantime, feel free to explore our platform:</p>
                <ul>
                    <li><a href="https://homeandown.com/buy" style="color: #2563eb;">Browse Properties for Sale</a></li>
                    <li><a href="https://homeandown.com/rent" style="color: #2563eb;">Find Rental Properties</a></li>
                    <li><a href="https://homeandown.com/sell" style="color: #2563eb;">List Your Property</a></li>
                </ul>
                
                <p>Best regards,<br>
                <strong>The Home & Own Team</strong></p>
                
                <hr style="border: none; border-top: 1px solid #ddd; margin: 20px 0;">
                <p style="color: #999; font-size: 12px; text-align: center;">
                    © 2025 Home & Own. All rights reserved.<br>
                    If you have any questions, reply to this email or visit our website.
                </p>
            </div>
        </body>
        </html>
        """
        
        email_result_user = await send_email(
            to=email,
            subject="We've Received Your Message - Home & Own",
            html=user_html
        )
        if email_result_user.get("status") == "sent":
            print(f"[RECORDS] ✅ Confirmation email sent to: {email} via {email_result_user.get('provider', 'unknown')}")
        else:
            print(f"[RECORDS] ⚠️ Confirmation email may have failed: {email_result_user.get('error', 'Unknown error')}")
        
        return {
            "success": True,
            "message": "Thank you for your message! We'll get back to you soon."
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[RECORDS] Contact form error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to process contact form: {str(e)}")


@router.get("/bookings")
async def get_bookings(user_id: str | None = None, property_id: str | None = None):
    try:
        print(f"[RECORDS] Fetching bookings user_id={user_id} property_id={property_id}")
        filters = {}
        if user_id:
            filters["user_id"] = user_id
        if property_id:
            filters["property_id"] = property_id

        bookings = await db.select("bookings") if not filters else await db.select("bookings", filters=filters)
        print(f"[RECORDS] Found {len(bookings)} bookings")
        return bookings or []
    except Exception as e:
        print(f"[RECORDS] Get bookings error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch bookings: {str(e)}")

@router.post("/inquiries")
async def create_inquiry(inquiry: InquiryRequest, request: Request):
    try:
        print(f"[RECORDS] Creating inquiry for property: {inquiry.property_id}")
        print(f"[RECORDS] Inquiry data: {inquiry.model_dump()}")
        
        # Try to get user_id from authentication if available
        user_id = None
        try:
            from ..core.security import try_get_current_user_claims
            claims = try_get_current_user_claims(request)
            if claims:
                user_id = claims.get("sub")
                print(f"[RECORDS] Found authenticated user: {user_id}")
        except Exception as auth_error:
            print(f"[RECORDS] No authentication found, creating anonymous inquiry: {auth_error}")
        
        inquiry_data = {
            "id": str(uuid.uuid4()),
            "property_id": inquiry.property_id,
            "name": inquiry.name,
            "email": inquiry.email,
            "phone": inquiry.phone,
            "message": inquiry.message,
            "inquiry_type": inquiry.inquiry_type,
            "status": "new",
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "updated_at": dt.datetime.now(dt.timezone.utc).isoformat()
        }
        
        # Link inquiry to user if authenticated
        if user_id:
            inquiry_data["user_id"] = user_id
            print(f"[RECORDS] Linking inquiry to user: {user_id}")
        
        # Get property details to find the owner/agent BEFORE inserting
        property_details = None
        try:
            properties = await db.select("properties", filters={"id": inquiry.property_id})
            if properties:
                property_details = properties[0]
                # Assign agent to inquiry if property has an agent (include in initial insert)
                # Use assigned_agent_id or agent_id from property
                agent_id = property_details.get("assigned_agent_id") or property_details.get("agent_id")
                if agent_id:
                    inquiry_data["assigned_agent_id"] = agent_id
                    print(f"[RECORDS] Property has agent {agent_id}, including in inquiry")
        except Exception as prop_error:
            print(f"[RECORDS] Error fetching property details: {prop_error}")
        
        print(f"[RECORDS] Prepared inquiry data: {inquiry_data}")
        created = await db.insert("inquiries", inquiry_data)
        print(f"[RECORDS] Inquiry created successfully: {created}")
        
        # Auto-assign agent based on property
        try:
            from ..services.agent_assignment import AgentAssignmentService
            inquiry_id = created[0]["id"] if isinstance(created, list) and created else inquiry_data["id"]
            assignment_result = await AgentAssignmentService.assign_agent_to_inquiry(inquiry_id, inquiry.property_id)
            if assignment_result.get('success'):
                print(f"[RECORDS] Agent assigned to inquiry: {assignment_result.get('message')}")
            else:
                print(f"[RECORDS] Agent assignment failed: {assignment_result.get('error')}")
        except Exception as assignment_error:
            print(f"[RECORDS] Agent assignment error: {assignment_error}")
        
        # Send email notifications
        try:
            # Send admin notification for new inquiry
            try:
                from ..services.admin_notification_service import AdminNotificationService
                await AdminNotificationService.notify_inquiry_submission(inquiry_data, property_details)
                print(f"[RECORDS] Admin notification sent for new inquiry: {inquiry.name}")
            except Exception as notify_error:
                print(f"[RECORDS] Failed to send admin notification: {notify_error}")
                # Fallback to old email system
                try:
                    subject_admin, html_admin = inquiry_email(True, inquiry.name or "", property_details, inquiry.property_id)
                    await send_email("info@homeandown.com", subject_admin, html_admin)
                    print(f"[RECORDS] Fallback admin email sent")
                except Exception as fallback_error:
                    print(f"[RECORDS] Fallback admin email failed: {fallback_error}")
            
            # Send to property agent only (not owner)
            if property_details and property_details.get("agent_id"):
                try:
                    # Get agent details
                    users = await db.select("users", filters={"id": property_details["agent_id"]})
                    if users and users[0].get("email"):
                        agent_email = users[0]["email"]
                        agent_name = f"{users[0].get('first_name', '')} {users[0].get('last_name', '')}".strip()
                        subject_agent, html_agent = inquiry_email(True, inquiry.name or "", property_details, inquiry.property_id, is_owner=True)
                        await send_email(agent_email, subject_agent, html_agent)
                        print(f"[RECORDS] ✅ Sent inquiry notification to agent {agent_name}: {agent_email}")
                except Exception as agent_error:
                    print(f"[RECORDS] Error sending email to agent: {agent_error}")
            
            # Send confirmation to user
            if inquiry.email:
                subject_user, html_user = inquiry_email(False, inquiry.name or "", property_details, inquiry.property_id)
                await send_email(inquiry.email, subject_user, html_user)
                print(f"[RECORDS] ✅ Sent confirmation email to user: {inquiry.email}")
        except Exception as email_error:
            print(f"[RECORDS] Email notification error: {email_error}")
        
        # Get additional details for response
        response_data = {
            "success": True,
            "message": f"Inquiry sent successfully for {property_details.get('title', 'property') if property_details else 'property'}. The agent will contact you soon.",
            "id": created[0]["id"] if isinstance(created, list) and created else inquiry_data["id"],
            "property_name": property_details.get("title", f"Property #{inquiry.property_id}") if property_details else f"Property #{inquiry.property_id}",
            "property_id": inquiry.property_id,
            "agent_name": None,
            "agent_email": None
        }
        
        # Get agent details if assigned
        if inquiry_data.get("assigned_agent_id"):
            try:
                agent_users = await db.select("users", filters={"id": inquiry_data["assigned_agent_id"]})
                if agent_users:
                    agent = agent_users[0]
                    response_data["agent_name"] = f"{agent.get('first_name', '')} {agent.get('last_name', '')}".strip()
                    response_data["agent_email"] = agent.get("email")
            except Exception as agent_error:
                print(f"[RECORDS] Error fetching agent details: {agent_error}")
        
        print("[RECORDS] Inquiry created successfully")
        return response_data
        
    except Exception as e:
        print(f"[RECORDS] Create inquiry error: {e}")
        import traceback
        print(f"[RECORDS] Full traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Failed to create inquiry: {str(e)}")

@router.post("/bookings")
async def create_booking(booking_data: dict, request: Request):
    try:
        print(f"[RECORDS] Creating booking for property: {booking_data.get('property_id')}")
        print(f"[RECORDS] Received booking data: {booking_data}")
        
        # Validate required fields
        required_fields = ['property_id', 'name', 'email', 'booking_date', 'booking_time']
        missing_fields = []
        
        for field in required_fields:
            if not booking_data.get(field):
                missing_fields.append(field)
        
        if missing_fields:
            print(f"[RECORDS] Missing required fields: {missing_fields}")
            raise HTTPException(status_code=400, detail=f"Missing required fields: {', '.join(missing_fields)}")
        
        # Handle preferred_time field (frontend sends this instead of booking_time)
        if 'preferred_time' in booking_data and not booking_data.get('booking_time'):
            booking_data['booking_time'] = booking_data['preferred_time']
            print(f"[RECORDS] Mapped preferred_time to booking_time: {booking_data['booking_time']}")
        
        # Try to get user_id from authentication if available
        user_id = None
        try:
            from ..core.security import try_get_current_user_claims
            claims = try_get_current_user_claims(request)
            if claims:
                user_id = claims.get("sub")  # JWT uses "sub" for user ID
                print(f"[RECORDS] Found authenticated user: {user_id}")
        except Exception as auth_error:
            print(f"[RECORDS] No authentication found, creating anonymous booking: {auth_error}")
        
        # If no user_id, check if user exists by email, otherwise create a temporary user record for anonymous bookings
        if not user_id:
            try:
                # Check if user already exists with this email
                existing_users = await db.select("users", filters={"email": booking_data['email']})
                if existing_users:
                    user_id = existing_users[0]["id"]
                    print(f"[RECORDS] Found existing user for email: {booking_data['email']}")
                else:
                    # Create a temporary user record for anonymous bookings
                    temp_user_data = {
                        "id": str(uuid.uuid4()),
                        "email": booking_data['email'],
                        "first_name": booking_data['name'].split()[0] if booking_data['name'] else "Guest",
                        "last_name": " ".join(booking_data['name'].split()[1:]) if booking_data['name'] and len(booking_data['name'].split()) > 1 else "",
                        "user_type": "buyer",
                        "status": "active",
                        "verification_status": "verified",
                        "email_verified": False,
                        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                        "updated_at": dt.datetime.now(dt.timezone.utc).isoformat()
                    }
                    
                    temp_user = await db.insert("users", temp_user_data)
                    user_id = temp_user_data["id"]
                    print(f"[RECORDS] Created temporary user for anonymous booking: {user_id}")
            except Exception as user_error:
                print(f"[RECORDS] Failed to handle user creation/lookup: {user_error}")
                import traceback
                print(f"[RECORDS] User error traceback: {traceback.format_exc()}")
                # Fallback: set user_id to None (database allows NULL for user_id)
                user_id = None
        
        # Format booking_date and booking_time properly
        booking_date_str = booking_data['booking_date']
        booking_time_str = booking_data['booking_time']
        
        # Ensure booking_date is in YYYY-MM-DD format
        try:
            # Parse and reformat date to ensure it's correct
            if isinstance(booking_date_str, str):
                # Try to parse the date to validate it
                parsed_date = dt.datetime.strptime(booking_date_str, "%Y-%m-%d").date()
                booking_date_formatted = parsed_date.isoformat()  # Returns YYYY-MM-DD
            else:
                booking_date_formatted = str(booking_date_str)
        except Exception as date_error:
            print(f"[RECORDS] Error parsing booking_date '{booking_date_str}': {date_error}")
            booking_date_formatted = booking_date_str  # Use as-is if parsing fails
        
        # Ensure booking_time is in HH:MM:SS format (or HH:MM)
        try:
            if isinstance(booking_time_str, str):
                # If time is in HH:MM format, add :00 for seconds
                if len(booking_time_str.split(':')) == 2:
                    booking_time_formatted = booking_time_str + ":00"
                else:
                    booking_time_formatted = booking_time_str
            else:
                booking_time_formatted = str(booking_time_str)
        except Exception as time_error:
            print(f"[RECORDS] Error parsing booking_time '{booking_time_str}': {time_error}")
            booking_time_formatted = booking_time_str  # Use as-is if parsing fails
        
        booking_record = {
            "id": str(uuid.uuid4()),
            "property_id": booking_data['property_id'],
            "user_id": user_id,
            "name": booking_data['name'],
            "email": booking_data['email'],
            "phone": booking_data.get('phone') or None,  # Use None instead of empty string
            "booking_date": booking_date_formatted,
            "booking_time": booking_time_formatted,
            "notes": booking_data.get('notes') or None,  # Use None instead of empty string
            "status": "pending",
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "updated_at": dt.datetime.now(dt.timezone.utc).isoformat()
        }
        
        print(f"[RECORDS] Attempting to insert booking with data: {booking_record}")
        try:
            created = await db.insert("bookings", booking_record)
            print(f"[RECORDS] Booking inserted successfully: {created}")
        except Exception as insert_error:
            print(f"[RECORDS] Database insert error: {insert_error}")
            import traceback
            print(f"[RECORDS] Insert error traceback: {traceback.format_exc()}")
            raise  # Re-raise to be caught by outer exception handler
        
        # db.insert returns a list, so get the first element and extract booking_id immediately
        created_booking = created[0] if created and isinstance(created, list) and len(created) > 0 else None
        booking_id = created_booking.get("id") if created_booking else booking_record.get("id")
        print(f"[RECORDS] Booking ID: {booking_id}")
        
        # Get property details to find the owner/agent
        property_details = None
        agent_id = None
        try:
            properties = await db.select("properties", filters={"id": booking_data['property_id']})
            if properties:
                property_details = properties[0]
                # Assign agent to booking if property has an agent (check both agent_id and assigned_agent_id)
                agent_id = property_details.get("assigned_agent_id") or property_details.get("agent_id")
                if agent_id:
                    # Update the booking with agent_id
                    try:
                        await db.update("bookings", {"agent_id": agent_id}, {"id": booking_id})
                        print(f"[RECORDS] Assigned agent {agent_id} to booking {booking_id}")
                    except Exception as update_error:
                        print(f"[RECORDS] Error updating booking with agent_id: {update_error}")
        except Exception as prop_error:
            print(f"[RECORDS] Error fetching property details: {prop_error}")
            import traceback
            print(f"[RECORDS] Property error traceback: {traceback.format_exc()}")
        
        # Send email notifications
        try:
            from ..services.email import send_email
            from ..services.templates import booking_confirmation_email, booking_notification_email
            
            if property_details:
                property_title = property_details.get('title', 'Property')
                booker_name = booking_data['name'] or "Guest User"
                booker_email = booking_data['email'] or "guest@example.com"
                
                # Get booker phone number
                booker_phone = booking_data.get('phone') or booking_record.get('phone', '')
                
                # Send confirmation email to booker
                confirmation_html = booking_confirmation_email(
                    booker_name,
                    property_title,
                    booking_data['booking_date'],
                    booking_data['booking_time'],
                    booker_phone
                )
                await send_email(
                    to=booker_email,
                    subject="Tour Booking Confirmed - Home & Own",
                    html=confirmation_html
                )
                print(f"[RECORDS] Confirmation email sent to: {booker_email}")
                
                # Send notification email to assigned agent (primary contact for inquiries/bookings)
                # agent_id is already set from property_details above
                if agent_id:
                    try:
                        agent_data = await db.select("users", filters={"id": agent_id})
                        if agent_data:
                            agent_info = agent_data[0]
                            agent_name = f"{agent_info.get('first_name', '')} {agent_info.get('last_name', '')}".strip()
                            agent_email = agent_info.get('email')
                            
                            if agent_email:
                                notification_html = booking_notification_email(
                                    agent_name,
                                    booker_name,
                                    booker_email,
                                    property_title,
                                    booking_data['booking_date'],
                                    booking_data['booking_time'],
                                    booker_phone
                                )
                                await send_email(
                                    to=agent_email,
                                    subject=f"New Tour Booking for {property_title} - Home & Own",
                                    html=notification_html
                                )
                                print(f"[RECORDS] ✅ Sent booking notification to agent {agent_name}: {agent_email}")
                                # Agent_id should already be set, but ensure it's updated if needed
                                if agent_id:
                                    try:
                                        await db.update("bookings", {"agent_id": agent_id}, {"id": booking_id})
                                    except Exception as update_error:
                                        print(f"[RECORDS] Error updating booking with agent_id: {update_error}")
                    except Exception as agent_error:
                        print(f"[RECORDS] Error sending email to agent: {agent_error}")
                        import traceback
                        print(f"[RECORDS] Agent error traceback: {traceback.format_exc()}")
                
                # Also send notification email to property owner (as secondary contact)
                if property_details.get('owner_id'):
                    try:
                        owner_data = await db.select("users", filters={"id": property_details.get('owner_id')})
                        if owner_data:
                            owner_info = owner_data[0]
                            owner_name = f"{owner_info.get('first_name', '')} {owner_info.get('last_name', '')}".strip()
                            owner_email = owner_info.get('email')
                            
                            if owner_email:
                                notification_html = booking_notification_email(
                                    owner_name,
                                    booker_name,
                                    booker_email,
                                    property_title,
                                    booking_data['booking_date'],
                                    booking_data['booking_time'],
                                    booker_phone
                                )
                                await send_email(
                                    to=owner_email,
                                    subject=f"New Tour Booking for {property_title} - Home & Own",
                                    html=notification_html
                                )
                                print(f"[RECORDS] ✅ Sent booking notification to owner: {owner_email}")
                    except Exception as owner_error:
                        print(f"[RECORDS] Error sending email to owner: {owner_error}")
        except Exception as email_error:
            print(f"[RECORDS] Email sending failed: {email_error}")
            # Don't fail the booking creation if email fails
        
        # Automatically create an inquiry when a booking is made
        try:
            inquiry_data = {
                "id": str(uuid.uuid4()),
                "property_id": booking_data['property_id'],
                "name": booking_data['name'],
                "email": booking_data['email'],
                "phone": booking_data.get('phone') or None,
                "message": f"Tour booking requested for {booking_data['booking_date']} at {booking_data['booking_time']}. " + (booking_data.get('notes') or ''),
                "inquiry_type": "booking",
                "status": "new",
                "user_id": user_id,
                "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                "updated_at": dt.datetime.now(dt.timezone.utc).isoformat()
            }
            
            # Assign agent to inquiry if property has an agent
            if agent_id:
                inquiry_data["assigned_agent_id"] = agent_id
            
            await db.insert("inquiries", inquiry_data)
            print(f"[RECORDS] ✅ Automatically created inquiry for booking: {inquiry_data['id']}")
        except Exception as inquiry_error:
            print(f"[RECORDS] Error creating inquiry for booking: {inquiry_error}")
            # Don't fail booking creation if inquiry creation fails
        
        # Send admin notification for new booking
        try:
            # Try to import AdminNotificationService if it exists
            try:
                from ..services.admin_notification_service import AdminNotificationService
                # Fetch user data for notification
                user_data_for_notification = None
                if user_id:
                    try:
                        user_records = await db.select("users", filters={"id": user_id})
                        if user_records:
                            user_data_for_notification = user_records[0]
                    except Exception as user_fetch_error:
                        print(f"[RECORDS] Error fetching user data for notification: {user_fetch_error}")
                
                await AdminNotificationService.notify_booking_submission(booking_record, property_details, user_data_for_notification)
                print(f"[RECORDS] Admin notification sent for new booking: {booking_data.get('name')}")
            except ImportError:
                print(f"[RECORDS] AdminNotificationService not available, skipping admin notification")
        except Exception as notify_error:
            print(f"[RECORDS] Failed to send admin notification: {notify_error}")
            import traceback
            print(f"[RECORDS] Notification error traceback: {traceback.format_exc()}")
            # Don't fail booking creation if notification fails
        
        # Get additional details for response
        response_data = {
            "success": True,
            "message": f"Tour booking confirmed for {property_details.get('title', 'property') if property_details else 'property'} on {booking_data['booking_date']} at {booking_data['booking_time']}",
            "id": booking_id,
            "property_name": property_details.get("title", f"Property #{booking_data['property_id']}") if property_details else f"Property #{booking_data['property_id']}",
            "booking_date": booking_data['booking_date'],
            "booking_time": booking_data['booking_time'],
            "agent_name": None,
            "agent_email": None
        }
        
        # Get agent details if assigned (use agent_id from property or booking)
        final_agent_id = agent_id or booking_record.get("agent_id")
        if final_agent_id:
            try:
                agent_users = await db.select("users", filters={"id": final_agent_id})
                if agent_users:
                    agent = agent_users[0]
                    response_data["agent_name"] = f"{agent.get('first_name', '')} {agent.get('last_name', '')}".strip()
                    response_data["agent_email"] = agent.get("email")
            except Exception as agent_error:
                print(f"[RECORDS] Error fetching agent details: {agent_error}")
        
        print("[RECORDS] Booking created successfully")
        return response_data
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[RECORDS] Create booking error: {e}")
        import traceback
        print(f"[RECORDS] Full traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Failed to create booking: {str(e)}")

@router.post("/properties")
async def create_property(prop: dict, _=Depends(require_api_key)):
    import time
    try:
        title = getattr(prop, 'title', '<no-title>')
        print(f"[RECORDS] Creating property: {title}")
        start_ts = time.perf_counter()

        property_data = {
            "id": str(uuid.uuid4()),
            "title": getattr(prop, 'title', '') if getattr(prop, 'title', None) is not None else '',
            "description": getattr(prop, 'description', ''),
            "price": getattr(prop, 'price', None),
            "monthly_rent": getattr(prop, 'monthly_rent', None),
            "security_deposit": getattr(prop, 'security_deposit', None),
            "property_type": getattr(prop, 'property_type', ''),
            "bedrooms": getattr(prop, 'bedrooms', None),
            "bathrooms": getattr(prop, 'bathrooms', None),
            "area_sqft": getattr(prop, 'area_sqft', None),
            "address": getattr(prop, 'address', ''),
            # Accept either name or id fields from frontend
            "city": getattr(prop, 'city', None),
            "state": getattr(prop, 'state', None),
            "state_id": getattr(prop, 'state_id', None),
            "district_id": getattr(prop, 'district_id', None),
            "mandal_id": getattr(prop, 'mandal_id', None),
            "zip_code": getattr(prop, 'zip_code', ''),
            "latitude": getattr(prop, 'latitude', None),
            "longitude": getattr(prop, 'longitude', None),
            "listing_type": getattr(prop, 'listing_type', ''),
            "furnishing_status": getattr(prop, 'furnishing_status', None),
            "available_from": getattr(prop, 'available_from', None),
            "status": "pending",  # Changed from active to pending for admin approval
            "featured": False,
            "verified": False,
            "amenities": getattr(prop, 'amenities', []) or [],
            "images": getattr(prop, 'images', []) or [],
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat()
        }

        # Diagnostic: which client and service-role validity
        try:
            print(f"[RECORDS] DB admin_client present: {bool(getattr(db, 'admin_client', None))}")
            print(f"[RECORDS] Supabase service-role probe valid: {getattr(db, '_service_role_valid', None)}")
        except Exception:
            pass

        # Store images in properties table
        if property_data.get("images") and isinstance(property_data["images"], list):
            # Convert list to JSON string for storage
            import json
            property_data["images_json"] = json.dumps(property_data["images"])
            print(f"[RECORDS] Storing {len(property_data['images'])} images in database")

        created = None
        insert_err = None
        try:
            created = await db.insert("properties", property_data)
            print(f"[RECORDS] db.insert returned rows: {len(created) if created else 0}")
        except Exception as e:
            insert_err = e
            print(f"[RECORDS] db.insert exception: {e}")

        elapsed = time.perf_counter() - start_ts
        print(f"[RECORDS] Insert elapsed time: {elapsed:.3f}s")

        # Send notification (best-effort)
        try:
            subject, html = notify_info("New property created", [f"Title: {title}", f"City: {getattr(prop,'city', '')}"])
            await send_email("info@homeandown.com", subject, html)
        except Exception as email_error:
            print(f"[RECORDS] Notification email error: {email_error}")

        if insert_err:
            # Fail fast and return a clear error to the client — avoids confusing optimistic success
            print(f"[RECORDS] Insert failed: {insert_err}")
            raise HTTPException(status_code=502, detail={
                "message": "Database insert failed",
                "hint": str(insert_err)
            })

        # Persist any provided sections (if sent by frontend)
        try:
            sections = getattr(prop, 'sections', None) or []
            if sections and created:
                # created can be a list with inserted row
                created_id = created[0]["id"] if isinstance(created, list) and created else property_data["id"]
                to_insert = []
                for idx, s in enumerate(sections):
                    to_insert.append({
                        "id": str(uuid.uuid4()),
                        "property_id": created_id,
                        "title": s.get('title') or '',
                        "content": s.get('content') or '',
                        "sort_order": idx,
                        "created_at": dt.datetime.now(dt.timezone.utc).isoformat()
                    })
                if to_insert:
                    await db.insert("property_sections", to_insert[0] if len(to_insert) == 1 else to_insert)
                    print(f"[RECORDS] ✅ Inserted {len(to_insert)} sections for property {created_id}")
        except Exception as sec_err:
            print(f"[RECORDS] ⚠️ Failed to persist sections: {sec_err}")

        print("[RECORDS] Property created successfully")
        return {"success": True, "id": created[0]["id"] if created else property_data["id"], "created_rows": created or []}

    except Exception as e:
        print(f"[RECORDS] Create property error: {e}")
        raise HTTPException(status_code=500, detail="Failed to create property")


@router.get("/users/{user_id}")
async def get_user(user_id: str):
    try:
        print(f"[RECORDS] Fetching user: {user_id}")
        users = await db.select("users", filters={"id": user_id})
        if not users:
            raise HTTPException(status_code=404, detail="User not found")
        
        user = users[0]
        # Remove sensitive data
        user_data = {
            "id": user.get("id"),
            "first_name": user.get("first_name"),
            "last_name": user.get("last_name"),
            "email": user.get("email"),
            "phone_number": user.get("phone_number"),
            "user_type": user.get("user_type"),
            "status": user.get("status")
        }
        
        print(f"[RECORDS] Found user: {user_data.get('first_name')} {user_data.get('last_name')}")
        return user_data
    except HTTPException:
        raise
    except Exception as e:
        print(f"[RECORDS] Get user error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch user: {str(e)}")

@router.get("/inquiries")
async def list_user_inquiries(user_id: str | None = None, property_id: str | None = None):
    try:
        print(f"[RECORDS] Fetching inquiries user_id={user_id} property_id={property_id}")
        filters = {}
        if user_id:
            filters["user_id"] = user_id
        if property_id:
            filters["property_id"] = property_id

        inquiries = await db.select("inquiries") if not filters else await db.select("inquiries", filters=filters)
        return inquiries or []
    except Exception as e:
        print(f"[RECORDS] List user inquiries error: {e}")
        raise HTTPException(status_code=500, detail="Failed to list inquiries")


@router.put("/bookings/{booking_id}")
async def update_booking(booking_id: str, update: BookingUpdateRequest):
    try:
        print(f"[RECORDS] Updating booking {booking_id} to status: {update.status}")

        # Get current booking
        bookings = await db.select("bookings", filters={"id": booking_id})
        if not bookings:
            raise HTTPException(status_code=404, detail="Booking not found")

        booking = bookings[0]
        update_data = {
            "status": update.status,
            "updated_at": dt.datetime.now(dt.timezone.utc).isoformat()
        }

        # Note: Database doesn't have status-specific timestamp fields
        # We'll just update the status and updated_at timestamp

        # Add agent notes if provided (store in notes field since agent_notes doesn't exist in DB)
        if update.agent_notes:
            update_data["notes"] = update.agent_notes

        # Update booking date/time if provided
        if update.booking_date:
            update_data["booking_date"] = update.booking_date
        if update.booking_time:
            update_data["booking_time"] = update.booking_time

        # Update agent_id if provided (allow assigning/unassigning agents)
        if hasattr(update, 'agent_id'):
            if update.agent_id is not None and update.agent_id != '':
                update_data["agent_id"] = update.agent_id
                print(f"[RECORDS] Assigning agent {update.agent_id} to booking {booking_id}")
            else:
                # Allow clearing agent assignment
                update_data["agent_id"] = None
                print(f"[RECORDS] Clearing agent assignment for booking {booking_id}")

        await db.update("bookings", update_data, filters={"id": booking_id})

        # Send email notifications
        property_details = None
        try:
            # Get property details
            properties = await db.select("properties", filters={"id": booking.get("property_id")})
            property_details = properties[0] if properties else None

            # Get customer details from user_id
            customer = None
            if booking.get("user_id"):
                users = await db.select("users", filters={"id": booking.get("user_id")})
                customer = users[0] if users else None

            # Send status update email to customer if we have their email
            # Check both user_id and booking email/name fields
            customer_email = None
            customer_name = None
            if customer and customer.get("email"):
                customer_email = customer.get("email")
                customer_name = f"{customer.get('first_name', '')} {customer.get('last_name', '')}".strip() or customer.get('email', 'Customer')
            elif booking.get("email"):
                customer_email = booking.get("email")
                customer_name = booking.get("name") or booking.get("email", "Customer")
            
            # Check if agent was just assigned (before we send any emails to avoid duplicates)
            agent_just_assigned = "agent_id" in update_data and update_data["agent_id"] and update_data["agent_id"] != booking.get("agent_id")
            
            if customer_email:
                try:
                    subject, html = booking_status_email(
                        booking, property_details, update.status, update.agent_notes
                    )
                    await send_email(customer_email, subject, html)
                    print(f"[RECORDS] ✅ Sent booking status update email to customer: {customer_email}")
                except Exception as customer_email_error:
                    print(f"[RECORDS] Error sending email to customer: {customer_email_error}")
                    import traceback
                    print(f"[RECORDS] Customer email error traceback: {traceback.format_exc()}")

            # Send notification to agent if status changed (but NOT if agent was just assigned - that gets a separate assignment email)
            # Use updated agent_id if it was changed, otherwise use existing
            agent_id_to_notify = update_data.get("agent_id") if "agent_id" in update_data else booking.get("agent_id")
            
            # Also check if property has an assigned agent
            if not agent_id_to_notify and property_details:
                agent_id_to_notify = property_details.get("agent_id") or property_details.get("assigned_agent_id")
            
            # Only send status update email to agent if agent exists and was NOT just assigned (to avoid duplicate)
            if agent_id_to_notify and not agent_just_assigned:
                try:
                    agent_users = await db.select("users", filters={"id": agent_id_to_notify})
                    if agent_users and agent_users[0].get("email"):
                        agent_email = agent_users[0]["email"]
                        agent_name = f"{agent_users[0].get('first_name', '')} {agent_users[0].get('last_name', '')}".strip() or "Agent"
                        agent_subject, agent_html = booking_status_email(
                            booking, property_details, update.status, update.agent_notes, is_agent=True
                        )
                        await send_email(agent_email, agent_subject, agent_html)
                        print(f"[RECORDS] ✅ Sent booking status update email to agent {agent_name}: {agent_email}")
                except Exception as agent_email_error:
                    print(f"[RECORDS] Error sending email to agent: {agent_email_error}")
                    import traceback
                    print(f"[RECORDS] Agent email error traceback: {traceback.format_exc()}")
            
            # Send notification to property owner/seller if status changed
            # Only send if owner is different from agent (to avoid duplicate emails)
            owner_id = property_details.get('owner_id') if property_details else None
            if owner_id:
                # Check if owner is also the agent (to avoid duplicate emails)
                agent_id_to_check = update_data.get("agent_id") if "agent_id" in update_data else booking.get("agent_id")
                if owner_id != agent_id_to_check:
                    try:
                        owner_data = await db.select("users", filters={"id": owner_id})
                        if owner_data:
                            owner_info = owner_data[0]
                            owner_name = f"{owner_info.get('first_name', '')} {owner_info.get('last_name', '')}".strip()
                            owner_email = owner_info.get("email")
                            
                            if owner_email:
                                # Use booking notification email template for owner
                                from ..services.templates import booking_notification_email
                                customer_phone = booking.get("phone") or (customer.get("phone_number") if customer else None)
                                owner_notification_html = booking_notification_email(
                                    owner_name,
                                    customer_name or booking.get("name", "Customer"),
                                    customer_email or booking.get("email", "N/A"),
                                    property_details.get("title", "Property") if property_details else "Property",
                                    booking.get("booking_date", "TBD"),
                                    booking.get("booking_time", "TBD"),
                                    customer_phone
                                )
                                await send_email(
                                    to=owner_email,
                                    subject=f"Booking Status Update - {property_details.get('title', 'Property') if property_details else 'Property'}",
                                    html=owner_notification_html
                                )
                                print(f"[RECORDS] ✅ Sent booking status update email to owner/seller {owner_name}: {owner_email}")
                    except Exception as owner_email_error:
                        print(f"[RECORDS] Error sending email to owner: {owner_email_error}")
                        import traceback
                        print(f"[RECORDS] Owner email error traceback: {traceback.format_exc()}")
            
            # If agent was just assigned, send assignment notification email (instead of status update)
            if agent_just_assigned:
                try:
                    new_agent_users = await db.select("users", filters={"id": update_data["agent_id"]})
                    if new_agent_users and new_agent_users[0].get("email"):
                        new_agent_email = new_agent_users[0]["email"]
                        new_agent_name = f"{new_agent_users[0].get('first_name', '')} {new_agent_users[0].get('last_name', '')}".strip() or "Agent"
                        
                        # Send assignment notification to agent
                        from ..services.templates import booking_notification_email
                        customer_phone = booking.get("phone") or customer.get("phone_number") if customer else None
                        assignment_html = booking_notification_email(
                            new_agent_name,
                            customer_name or "Customer",
                            customer_email or booking.get("email", "N/A"),
                            property_details.get("title", "Property") if property_details else "Property",
                            booking.get("booking_date", "TBD"),
                            booking.get("booking_time", "TBD"),
                            customer_phone
                        )
                        await send_email(
                            to=new_agent_email,
                            subject=f"New Booking Assignment - {property_details.get('title', 'Property') if property_details else 'Property'}",
                            html=assignment_html
                        )
                        print(f"[RECORDS] ✅ Sent booking assignment email to agent {new_agent_name}: {new_agent_email}")
                        
                        # Also notify customer that agent has been assigned
                        if customer_email:
                            customer_assignment_html = f"""
                            <!DOCTYPE html>
                            <html>
                            <head>
                                <meta charset="utf-8">
                                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                            </head>
                            <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 0; background-color: #f5f5f5;">
                                <div style="max-width: 600px; margin: 40px auto; background-color: white; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);">
                                    <div style="background: linear-gradient(135deg, #2563eb 0%, #1e40af 100%); padding: 40px 20px; text-align: center;">
                                        <h1 style="color: white; margin: 0; font-size: 28px; font-weight: 700;">Agent Assigned</h1>
                                    </div>
                                    <div style="padding: 40px 30px;">
                                        <h2 style="color: #1e293b; margin: 0 0 20px 0; font-size: 24px;">Hello {customer_name},</h2>
                                        <p style="color: #475569; font-size: 16px; line-height: 1.6; margin: 0 0 20px 0;">
                                            Great news! An agent has been assigned to your booking for <strong>{property_details.get('title', 'the property') if property_details else 'the property'}</strong>.
                                        </p>
                                        <p style="color: #475569; font-size: 16px; line-height: 1.6; margin: 0 0 20px 0;">
                                            <strong>Assigned Agent:</strong> {new_agent_name}
                                        </p>
                                        <p style="color: #475569; font-size: 16px; line-height: 1.6; margin: 0 0 20px 0;">
                                            Your agent will be in touch with you shortly regarding your tour booking scheduled for <strong>{booking.get('booking_date', 'TBD')}</strong> at <strong>{booking.get('booking_time', 'TBD')}</strong>.
                                        </p>
                                    </div>
                                </div>
                            </body>
                            </html>
                            """
                            await send_email(
                                to=customer_email,
                                subject=f"Agent Assigned to Your Booking - {property_details.get('title', 'Property') if property_details else 'Property'}",
                                html=customer_assignment_html
                            )
                            print(f"[RECORDS] ✅ Sent agent assignment notification to customer: {customer_email}")
                except Exception as assignment_error:
                    print(f"[RECORDS] Error sending assignment notification: {assignment_error}")

        except Exception as email_error:
            print(f"[RECORDS] Email notification error: {email_error}")

        # Enhanced response with names
        customer_name = "Unknown"
        if customer:
            customer_name = f"{customer.get('first_name', '')} {customer.get('last_name', '')}".strip() or customer.get('email', 'Unknown')
        
        response_data = {
            "success": True,
            "message": f"Booking {update.status}",
            "booking_id": booking_id,
            "customer_name": customer_name,
            "property_name": property_details.get("title", f"Property #{booking.get('property_id')}") if property_details else f"Property #{booking.get('property_id')}",
            "agent_name": None
        }
        
        # Add agent name if assigned (use updated agent_id if changed)
        agent_id_for_response = update_data.get("agent_id") if "agent_id" in update_data else booking.get("agent_id")
        if agent_id_for_response:
            try:
                agent_users = await db.select("users", filters={"id": agent_id_for_response})
                if agent_users:
                    agent = agent_users[0]
                    response_data["agent_name"] = f"{agent.get('first_name', '')} {agent.get('last_name', '')}".strip()
                    response_data["agent_id"] = agent_id_for_response
            except Exception as agent_error:
                print(f"[RECORDS] Error fetching agent details: {agent_error}")
        else:
            response_data["agent_id"] = None
            response_data["agent_name"] = None
        
        return response_data
    except Exception as e:
        print(f"[RECORDS] Update booking error: {e}")
        raise HTTPException(status_code=500, detail="Failed to update booking")


@router.post("/owner-agent/contact")
async def owner_contact_agent(data: dict, request: Request):
    """Property owner contacts assigned agent"""
    try:
        print(f"[RECORDS] Owner contacting agent")
        
        property_id = data.get("property_id")
        owner_id = data.get("owner_id")
        message = data.get("message")
        subject = data.get("subject", "Message from Property Owner")
        
        if not property_id or not owner_id or not message:
            raise HTTPException(status_code=400, detail="property_id, owner_id, and message are required")
        
        # Get property and verify owner
        properties = await db.select("properties", filters={"id": property_id})
        if not properties:
            raise HTTPException(status_code=404, detail="Property not found")
        
        property_data = properties[0]
        property_owner_id = property_data.get("owner_id") or property_data.get("added_by")
        
        if property_owner_id != owner_id:
            raise HTTPException(status_code=403, detail="Not authorized - you are not the owner of this property")
        
        # Get assigned agent
        agent_id = property_data.get("assigned_agent_id") or property_data.get("agent_id")
        if not agent_id:
            raise HTTPException(status_code=404, detail="No agent assigned to this property")
        
        # Get agent details
        agents = await db.select("users", filters={"id": agent_id})
        if not agents:
            raise HTTPException(status_code=404, detail="Agent not found")
        
        agent = agents[0]
        agent_email = agent.get("email")
        agent_name = f"{agent.get('first_name', '')} {agent.get('last_name', '')}".strip()
        
        # Get owner details
        owners = await db.select("users", filters={"id": owner_id})
        owner_name = "Property Owner"
        owner_email = ""
        if owners:
            owner = owners[0]
            owner_name = f"{owner.get('first_name', '')} {owner.get('last_name', '')}".strip()
            owner_email = owner.get("email", "")
        
        # Create inquiry record for owner-agent communication
        inquiry_data = {
            "id": str(uuid.uuid4()),
            "property_id": property_id,
            "name": owner_name,
            "email": owner_email,
            "phone": None,
            "message": message,
            "inquiry_type": "owner_agent",
            "status": "new",
            "assigned_agent_id": agent_id,
            "user_id": owner_id,
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "updated_at": dt.datetime.now(dt.timezone.utc).isoformat()
        }
        
        await db.insert("inquiries", inquiry_data)
        print(f"[RECORDS] Created owner-agent inquiry: {inquiry_data['id']}")
        
        # Send email to agent
        try:
            from ..services.email import send_email
            
            email_html = f"""
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                    <h2 style="color: #0ca5e9;">Message from Property Owner</h2>
                    <p>Dear {agent_name},</p>
                    <p>You have received a message from the owner of property: <strong>{property_data.get('title', 'N/A')}</strong></p>
                    <div style="background-color: #f5f5f5; padding: 15px; border-radius: 5px; margin: 20px 0;">
                        <p style="margin: 0;"><strong>Message:</strong></p>
                        <p style="margin: 10px 0 0 0;">{message}</p>
                    </div>
                    <p><strong>Property Owner:</strong> {owner_name}</p>
                    {f'<p><strong>Owner Email:</strong> {owner_email}</p>' if owner_email else ''}
                    <p>Please respond to this inquiry through your agent dashboard.</p>
                    <p>Best regards,<br>Home & Own Team</p>
                </div>
            </body>
            </html>
            """
            
            await send_email(agent_email, subject, email_html)
            print(f"[RECORDS] ✅ Owner-agent message sent to agent: {agent_email}")
        except Exception as email_error:
            print(f"[RECORDS] Error sending email to agent: {email_error}")
            # Don't fail if email fails
        
        return {"success": True, "message": "Message sent to agent successfully", "inquiry_id": inquiry_data["id"]}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[RECORDS] Owner contact agent error: {e}")
        import traceback
        print(f"[RECORDS] Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Failed to send message: {str(e)}")

@router.post("/inquiries/respond")
async def respond_to_inquiry(data: dict, request: Request):
    """Agent responds to an inquiry - sends email to client"""
    try:
        print(f"[RECORDS] Responding to inquiry")
        
        inquiry_id = data.get("inquiry_id")
        to_email = data.get("to")
        subject = data.get("subject", "Re: Your property inquiry")
        message = data.get("message")
        property_id = data.get("property_id")
        
        if not inquiry_id or not to_email or not message:
            raise HTTPException(status_code=400, detail="inquiry_id, to, and message are required")
        
        # Get inquiry details
        inquiries = await db.select("inquiries", filters={"id": inquiry_id})
        if not inquiries:
            raise HTTPException(status_code=404, detail="Inquiry not found")
        
        inquiry = inquiries[0]
        
        # Get property details
        property_details = None
        if property_id:
            properties = await db.select("properties", filters={"id": property_id})
            if properties:
                property_details = properties[0]
        
        # Send email to client
        try:
            from ..services.email import send_email
            from ..services.templates import inquiry_response_email
            
            # Create email HTML
            email_html = f"""
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                    <h2 style="color: #0ca5e9;">Response to Your Inquiry</h2>
                    <p>Dear {inquiry.get('name', 'Client')},</p>
                    <p>{message}</p>
                    {f'<p><strong>Property:</strong> {property_details.get("title", "N/A") if property_details else "N/A"}</p>' if property_details else ''}
                    <p>Best regards,<br>Home & Own Team</p>
                </div>
            </body>
            </html>
            """
            
            await send_email(to_email, subject, email_html)
            print(f"[RECORDS] ✅ Response email sent to: {to_email}")
            
            # Update inquiry status to contacted if it's new
            # Note: inquiries table doesn't have contacted_at column, only status and updated_at
            if inquiry.get("status") == "new":
                await db.update("inquiries", {
                    "status": "contacted",
                    "updated_at": dt.datetime.now(dt.timezone.utc).isoformat()
                }, {"id": inquiry_id})
                print(f"[RECORDS] Updated inquiry status to contacted")
            
        except Exception as email_error:
            print(f"[RECORDS] Error sending response email: {email_error}")
            raise HTTPException(status_code=500, detail=f"Failed to send email: {str(email_error)}")
        
        return {"success": True, "message": "Response sent successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[RECORDS] Respond to inquiry error: {e}")
        import traceback
        print(f"[RECORDS] Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Failed to respond to inquiry: {str(e)}")

@router.put("/inquiries/{inquiry_id}")
async def update_inquiry(inquiry_id: str, update: InquiryUpdateRequest):
    try:
        print(f"[RECORDS] Updating inquiry {inquiry_id} to status: {update.status}")

        # Get current inquiry
        inquiries = await db.select("inquiries", filters={"id": inquiry_id})
        if not inquiries:
            raise HTTPException(status_code=404, detail="Inquiry not found")

        inquiry = inquiries[0]
        update_data = {
            "status": update.status,
            "updated_at": dt.datetime.now(dt.timezone.utc).isoformat()
        }

        # Note: The inquiries table doesn't have status-specific timestamp columns
        # (contacted_at, confirmed_at, cancelled_at, completed_at) or agent_notes column
        # We only update status and updated_at timestamp
        
        # If agent notes are provided, we can store them in the message field or notes field
        # But since inquiries table doesn't have agent_notes, we'll skip it
        # The agent can add notes in the message field if needed

        print(f"[RECORDS] Updating inquiry with data: {update_data}")
        print(f"[RECORDS] Using filter: id={inquiry_id}")
        
        try:
            update_result = await db.update("inquiries", update_data, filters={"id": inquiry_id})
            print(f"[RECORDS] Update result: {update_result}")
        except Exception as update_error:
            print(f"[RECORDS] Database update error: {update_error}")
            import traceback
            print(f"[RECORDS] Update error traceback: {traceback.format_exc()}")
            raise HTTPException(status_code=500, detail=f"Database update failed: {str(update_error)}")

        # Send email notifications
        property_details = None
        try:
            # Get property details
            properties = await db.select("properties", filters={"id": inquiry.get("property_id")})
            property_details = properties[0] if properties else None

            # Send status update email to customer (only if email exists)
            inquiry_email = inquiry.get("email")
            if inquiry_email:
                try:
                    subject, html = inquiry_status_email(
                        inquiry, property_details, update.status, update.agent_notes
                    )
                    await send_email(inquiry_email, subject, html)
                    print(f"[RECORDS] ✅ Sent status update email to customer: {inquiry_email}")
                except Exception as customer_email_error:
                    print(f"[RECORDS] Error sending email to customer: {customer_email_error}")
                    import traceback
                    print(f"[RECORDS] Customer email error traceback: {traceback.format_exc()}")

            # Send notification to agent if status changed
            if inquiry.get("assigned_agent_id"):
                try:
                    agent_users = await db.select("users", filters={"id": inquiry.get("assigned_agent_id")})
                    if agent_users and agent_users[0].get("email"):
                        agent_email = agent_users[0]["email"]
                        agent_subject, agent_html = inquiry_status_email(
                            inquiry, property_details, update.status, update.agent_notes, is_agent=True
                        )
                        await send_email(agent_email, agent_subject, agent_html)
                        print(f"[RECORDS] ✅ Sent status update email to agent: {agent_email}")
                except Exception as agent_email_error:
                    print(f"[RECORDS] Error sending email to agent: {agent_email_error}")
                    import traceback
                    print(f"[RECORDS] Agent email error traceback: {traceback.format_exc()}")

        except Exception as email_error:
            print(f"[RECORDS] Email notification error: {email_error}")
            import traceback
            print(f"[RECORDS] Email error traceback: {traceback.format_exc()}")
            # Don't fail the update if email fails

        # Enhanced response with names
        property_name = f"Property #{inquiry.get('property_id')}"
        if property_details:
            property_name = property_details.get("title", property_name)
        
        response_data = {
            "success": True,
            "message": f"Inquiry {update.status}",
            "inquiry_id": inquiry_id,
            "customer_name": inquiry.get("name", "Unknown"),
            "property_name": property_name,
            "agent_name": None
        }
        
        # Add agent name if assigned
        if inquiry.get("agent_id"):
            try:
                agent_users = await db.select("users", filters={"id": inquiry.get("agent_id")})
                if agent_users:
                    agent = agent_users[0]
                    response_data["agent_name"] = f"{agent.get('first_name', '')} {agent.get('last_name', '')}".strip()
            except Exception as agent_error:
                print(f"[RECORDS] Error fetching agent details: {agent_error}")
        
        print(f"[RECORDS] ✅ Inquiry {inquiry_id} updated successfully to status: {update.status}")
        return response_data
    except HTTPException:
        raise
    except Exception as e:
        print(f"[RECORDS] ❌ Update inquiry error: {e}")
        import traceback
        print(f"[RECORDS] Update inquiry error traceback: {traceback.format_exc()}")
        # Return a more detailed error message
        error_detail = f"Failed to update inquiry: {str(e)}"
        print(f"[RECORDS] Raising HTTPException with detail: {error_detail}")
        raise HTTPException(status_code=500, detail=error_detail)


@router.delete("/bookings/{booking_id}")
async def delete_booking(booking_id: str, _=Depends(require_api_key)):
    """Delete a booking (hard delete)"""
    try:
        print(f"[RECORDS] Deleting booking: {booking_id}")
        
        # Check if booking exists
        bookings = await db.select("bookings", filters={"id": booking_id})
        if not bookings:
            raise HTTPException(status_code=404, detail="Booking not found")
        
        # Delete booking
        await db.delete("bookings", {"id": booking_id})
        
        print(f"[RECORDS] Booking deleted successfully: {booking_id}")
        return {"success": True, "message": "Booking deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[RECORDS] Delete booking error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete booking: {str(e)}")


@router.delete("/inquiries/{inquiry_id}")
async def delete_inquiry(inquiry_id: str, _=Depends(require_api_key)):
    """Delete an inquiry (hard delete)"""
    try:
        print(f"[RECORDS] Deleting inquiry: {inquiry_id}")
        
        # Check if inquiry exists
        inquiries = await db.select("inquiries", filters={"id": inquiry_id})
        if not inquiries:
            raise HTTPException(status_code=404, detail="Inquiry not found")
        
        # Delete inquiry
        await db.delete("inquiries", {"id": inquiry_id})
        
        print(f"[RECORDS] Inquiry deleted successfully: {inquiry_id}")
        return {"success": True, "message": "Inquiry deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[RECORDS] Delete inquiry error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete inquiry: {str(e)}")


@router.get("/notifications")
async def get_user_notifications(user_id: str, read: bool | None = None, limit: int = 50):
    """Get notifications for a specific user - optimized for speed"""
    import time
    start_time = time.time()
    
    try:
        # Check cache first (30 second cache)
        from ..core.cache import cache
        cache_key = f"notifications:{user_id}:{read}:{limit}"
        cached_result = cache.get(cache_key)
        if cached_result is not None:
            elapsed = (time.time() - start_time) * 1000
            print(f"[RECORDS] Notifications cache hit for user {user_id} ({elapsed:.0f}ms)")
            return cached_result
        
        print(f"[RECORDS] Fetching notifications for user: {user_id}, limit: {limit}")
        
        filters = {"user_id": user_id}
        if read is not None:
            filters["read"] = read
        
        # Add timeout to prevent hanging
        import asyncio
        try:
            # Add limit to prevent fetching all notifications (performance optimization)
            notifications = await asyncio.wait_for(
                db.select("notifications", filters=filters, limit=min(limit, 50), order_by="created_at", ascending=False),
                    timeout=1.5  # 1.5 second timeout for faster response
            )
        except asyncio.TimeoutError:
            print(f"[RECORDS] Notifications query timeout for user {user_id}")
            # Return cached result if available, otherwise empty
            if cached_result is not None:
                return cached_result
            return []
        
        result = notifications or []
        
        # Cache result for 60 seconds (longer cache for faster repeated requests)
        cache.set(cache_key, result, ttl=60)
        
        elapsed = (time.time() - start_time) * 1000
        print(f"[RECORDS] Notifications fetched for user {user_id} ({elapsed:.0f}ms, {len(result)} notifications)")
        
        return result
        
    except Exception as e:
        print(f"[RECORDS] Get notifications error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch notifications: {str(e)}")


@router.post("/notifications/{notification_id}/mark-read")
async def mark_notification_read(notification_id: str, user_id: str):
    """Mark a notification as read for a specific user"""
    try:
        print(f"[RECORDS] Marking notification as read: {notification_id} for user: {user_id}")
        
        # Verify the notification belongs to the user
        notifications = await db.select("notifications", filters={"id": notification_id, "user_id": user_id})
        if not notifications:
            raise HTTPException(status_code=404, detail="Notification not found")
        
        await db.update("notifications", {
            "read": True,
            "updated_at": dt.datetime.now(dt.timezone.utc).isoformat()
        }, {"id": notification_id})
        
        return {"success": True, "message": "Notification marked as read"}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[RECORDS] Mark notification read error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to mark notification as read: {str(e)}")


@router.post("/notifications/mark-all-read")
async def mark_all_notifications_read(user_id: str):
    """Mark all notifications as read for a specific user"""
    try:
        print(f"[RECORDS] Marking all notifications as read for user: {user_id}")
        
        await db.update("notifications", {
            "read": True,
            "updated_at": dt.datetime.now(dt.timezone.utc).isoformat()
        }, {"user_id": user_id, "read": False})
        
        return {"success": True, "message": "All notifications marked as read"}
        
    except Exception as e:
        print(f"[RECORDS] Mark all notifications read error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to mark all notifications as read: {str(e)}")


@router.delete("/notifications/{notification_id}")
async def delete_notification(notification_id: str, user_id: str):
    """Delete a notification for a specific user"""
    try:
        print(f"[RECORDS] Deleting notification: {notification_id} for user: {user_id}")
        
        # Verify the notification belongs to the user
        notifications = await db.select("notifications", filters={"id": notification_id, "user_id": user_id})
        if not notifications:
            raise HTTPException(status_code=404, detail="Notification not found")
        
        await db.delete("notifications", {"id": notification_id})
        
        return {"success": True, "message": "Notification deleted"}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[RECORDS] Delete notification error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete notification: {str(e)}")
