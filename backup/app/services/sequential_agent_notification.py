"""
Sequential Agent Notification Service
Handles sequential agent notifications with 5-minute timeout per agent,
up to 3 attempts per agent, for property assignments
"""

import asyncio
import datetime as dt
from typing import Dict, List, Optional, Any
from ..db.supabase_client import db
import uuid
import traceback

class SequentialAgentNotificationService:
    """Service for sequential agent notification with timeout handling"""
    
    # Active notification timers (property_id -> timer_task)
    _active_timers: Dict[str, asyncio.Task] = {}
    
    @staticmethod
    async def start_property_assignment_queue(property_id: str) -> Dict[str, Any]:
        """
        Start sequential notification process when property is approved
        This is triggered when admin approves a property
        """
        try:
            print(f"[SEQUENTIAL_NOTIFICATION] Starting assignment queue for property: {property_id}")
            
            # Get property details
            properties = await db.select("properties", filters={"id": property_id})
            if not properties:
                return {"success": False, "error": "Property not found"}
            
            property_data = properties[0]
            zip_code = property_data.get("zip_code")
            property_city = property_data.get("city")
            property_state = property_data.get("state")
            
            if not zip_code:
                print(f"[SEQUENTIAL_NOTIFICATION] Property {property_id} has no zip_code, marking as unassigned")
                return {
                    "success": False, 
                    "error": "Property has no zip code",
                    "unassigned": True
                }
            
            # Find all agents - first by zipcode, then by city/state if needed
            agents = await SequentialAgentNotificationService._find_agents_by_zipcode(zip_code)
            
            # If no agents found by zipcode, try city/state matching
            if not agents and property_city and property_state:
                print(f"[SEQUENTIAL_NOTIFICATION] No agents by zipcode, trying city/state match: {property_city}, {property_state}")
                agents = await SequentialAgentNotificationService._find_agents_by_location(property_city, property_state)
            
            if not agents:
                print(f"[SEQUENTIAL_NOTIFICATION] No agents found for zipcode {zip_code}")
                return {
                    "success": False,
                    "error": "No agents available in this area",
                    "unassigned": True
                }
            
            print(f"[SEQUENTIAL_NOTIFICATION] Found {len(agents)} agents for zipcode {zip_code}")
            
            # Create assignment queue entry
            agent_list = [{"id": str(agent["id"]), "name": f"{agent.get('first_name', '')} {agent.get('last_name', '')}"} for agent in agents]
            
            queue_data = {
                "id": str(uuid.uuid4()),
                "property_id": property_id,
                "status": "active",
                "current_round": 1,
                "agent_list": agent_list,
                "started_at": dt.datetime.utcnow().isoformat(),
                "created_at": dt.datetime.utcnow().isoformat(),
                "updated_at": dt.datetime.utcnow().isoformat()
            }
            
            await db.insert("property_assignment_queue", queue_data)
            print(f"[SEQUENTIAL_NOTIFICATION] Created assignment queue for property {property_id}")
            
            # Start the sequential notification process immediately
            print(f"[SEQUENTIAL_NOTIFICATION] Creating async task to process queue for property {property_id}")
            
            # CRITICAL: Call _process_queue directly to ensure it runs immediately
            # Using asyncio.create_task might not execute immediately in FastAPI's event loop
            try:
                # Try to process the queue immediately in the current context
                await SequentialAgentNotificationService._process_queue(property_id)
                print(f"[SEQUENTIAL_NOTIFICATION] Queue processing initiated successfully for property {property_id}")
            except Exception as immediate_error:
                print(f"[SEQUENTIAL_NOTIFICATION] CRITICAL ERROR starting queue: {immediate_error}")
                traceback.print_exc()
                # Don't fail the whole operation, but log it
                pass
            
            return {
                "success": True,
                "message": f"Notification queue started for {len(agents)} agents",
                "agents_count": len(agents),
                "queue_id": queue_data["id"]
            }
            
        except Exception as e:
            print(f"[SEQUENTIAL_NOTIFICATION] Error starting assignment queue: {e}")
            print(traceback.format_exc())
            return {"success": False, "error": str(e)}
    
    @staticmethod
    async def _find_agents_by_zipcode(zip_code: str) -> List[Dict[str, Any]]:
        """
        Find all agents in the same zipcode
        Note: If users table doesn't have zip_code field, we'll match by city/state
        """
        try:
            # Get all verified active agents
            all_agents = await db.select("users", filters={
                "user_type": "agent",
                "status": "active",
                "verification_status": "verified"
            })
            
            if not all_agents:
                return []
            
            matching_agents = []
            
            # Try to match by zip_code first (if field exists)
            for agent in all_agents:
                agent_zip = agent.get("zip_code")
                if agent_zip and str(agent_zip).strip() == str(zip_code).strip():
                    matching_agents.append(agent)
            
            # If no direct zipcode match and we have property data, try city/state matching
            # This will be handled in start_property_assignment_queue where we have property data
            # For now, return agents matched by zip_code
            
            # If still no matches, try to get pincode location and match nearby agents
            if not matching_agents:
                # Try to find agents by nearby location (within same city)
                # We can use property's city/state to find agents
                print(f"[SEQUENTIAL_NOTIFICATION] No direct zipcode match, will match by property location")
                # Return empty for now, caller will handle city/state matching
                
            return matching_agents
            
        except Exception as e:
            print(f"[SEQUENTIAL_NOTIFICATION] Error finding agents by zipcode: {e}")
            print(traceback.format_exc())
            return []
    
    @staticmethod
    async def _find_agents_by_location(city: str, state: str) -> List[Dict[str, Any]]:
        """Find agents by city and state (fallback when zipcode doesn't match)"""
        try:
            agents = await db.select("users", filters={
                "user_type": "agent",
                "status": "active",
                "verification_status": "verified",
                "city": city,
                "state": state
            })
            return agents or []
        except Exception as e:
            print(f"[SEQUENTIAL_NOTIFICATION] Error finding agents by location: {e}")
            return []
    
    @staticmethod
    async def _process_queue(property_id: str):
        """
        Processes the notification queue. This function is designed to be called
        when the queue starts, and after each agent action (reject/timeout).
        """
        try:
            print(f"[QUEUE] Processing queue for property: {property_id}")

            queue_res = await db.select("property_assignment_queue", filters={"property_id": property_id})
            if not queue_res or queue_res[0].get("status") != "active":
                print(f"[QUEUE] Queue for property {property_id} is not active or not found. Stopping.")
                return

            queue = queue_res[0]
            
            prop_res = await db.select("properties", filters={"id": property_id})
            if not prop_res or prop_res[0].get("agent_id"):
                print(f"[QUEUE] Property {property_id} is already assigned. Stopping queue.")
                await db.update("property_assignment_queue", {"status": "completed"}, {"id": queue['id']})
                return

            next_agent_id = await SequentialAgentNotificationService._get_next_agent(property_id, queue)

            if next_agent_id:
                print(f"[QUEUE] Next agent to notify for property {property_id} is {next_agent_id}.")
                notification_result = await SequentialAgentNotificationService._send_notification_to_agent(property_id, next_agent_id, queue)
                print(f"[QUEUE] Notification result: {notification_result}")
                
                if not notification_result.get("success"):
                    print(f"[QUEUE] WARNING: Failed to send notification: {notification_result.get('error')}")
            else:
                print(f"[QUEUE] No more agents available for property {property_id}. Marking as unassigned.")
                await db.update("properties", {"status": "pending_unassigned"}, {"id": property_id})
                await db.update("property_assignment_queue", {"status": "completed_unassigned"}, {"id": queue['id']})

        except Exception as e:
            print(f"[QUEUE] CRITICAL ERROR in _process_queue for property {property_id}: {e}")
            traceback.print_exc()

    @staticmethod
    async def _get_next_agent(property_id: str, queue_data: Dict[str, Any]) -> Optional[str]:
        """
        Gets the next agent in a round-robin fashion.
        Increments the round if all agents in the current round have been notified.
        """
        agent_list = queue_data.get("agent_list", [])
        if not agent_list:
            return None

        last_notified_index = queue_data.get("last_notified_index", -1)
        current_round = queue_data.get("current_round", 1)

        if current_round > 3:
            return None # Max rounds reached

        next_index = (last_notified_index + 1) % len(agent_list)

        # If we have looped back to the start, it's time for the next round
        if next_index == 0 and last_notified_index != -1:
            current_round += 1
            if current_round > 3:
                return None # Max rounds reached
            await db.update("property_assignment_queue", {"current_round": current_round}, {"id": queue_data["id"]})

        next_agent_id = agent_list[next_index].get("id")
        
        # Update the queue with the index of the agent we are about to notify
        await db.update("property_assignment_queue", {"last_notified_index": next_index}, {"id": queue_data["id"]})
        
        return next_agent_id
    
    @staticmethod
    async def _send_notification_to_agent(
        property_id: str, 
        agent_id: str, 
        queue_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Send email notification to agent"""
        try:
            # Get agent details
            agents = await db.select("users", filters={"id": agent_id})
            if not agents:
                return {"success": False, "error": "Agent not found"}
            
            agent = agents[0]
            
            # Get property details
            properties = await db.select("properties", filters={"id": property_id})
            if not properties:
                return {"success": False, "error": "Property not found"}
            
            property_data = properties[0]
            
            # Calculate notification round for this agent
            existing_notifications = await db.select("agent_property_notifications",
                filters={"property_id": property_id, "agent_id": agent_id})
            notification_round = len(existing_notifications) + 1
            
            # Calculate expiration time (5 minutes from now)
            sent_at = dt.datetime.utcnow()
            expires_at = sent_at + dt.timedelta(minutes=5)
            
            # Generate secure token for this notification (allows accept/reject without login)
            import hashlib
            import secrets
            secure_token = secrets.token_urlsafe(32)  # 32-byte secure random token
            
            # Create notification record
            notification_id = str(uuid.uuid4())
            notification_data = {
                "id": notification_id,
                "property_id": property_id,
                "agent_id": agent_id,
                "notification_round": notification_round,
                "status": "pending",
                "sent_at": sent_at.isoformat(),
                "expires_at": expires_at.isoformat(),
                "email_sent": False,
                "secure_token": secure_token,  # Add secure token for authentication-free access
                "created_at": sent_at.isoformat(),
                "updated_at": sent_at.isoformat()
            }
            
            await db.insert("agent_property_notifications", notification_data)
            
            # Update queue
            await db.update("property_assignment_queue", {
                "current_agent_id": agent_id,
                "current_notification_id": notification_id,
                "total_notifications_sent": queue_data.get("total_notifications_sent", 0) + 1,
                "total_agents_contacted": len(set([
                    n.get("agent_id") for n in await db.select("agent_property_notifications", 
                        filters={"property_id": property_id})
                ])),
                "updated_at": dt.datetime.utcnow().isoformat()
            }, {"property_id": property_id})
            
            # Send email
            print(f"[SEQUENTIAL_NOTIFICATION] Preparing to send email to agent {agent_id}")
            from ..services.email import send_email
            from ..services.templates import get_property_assignment_email
            
            # Get base URL for accept/reject links (use frontend URL)
            base_url = "https://homeandown.com"  # This should match your frontend URL
            
            agent_email = agent.get("email")
            if not agent_email:
                print(f"[SEQUENTIAL_NOTIFICATION] ERROR: Agent {agent_id} has no email address!")
                return {"success": False, "error": "Agent has no email address"}
            
            print(f"[SEQUENTIAL_NOTIFICATION] Generating email template for {agent_email}")
            # Include secure token in URL for authentication-free access
            email_html = await get_property_assignment_email(
                agent_name=f"{agent.get('first_name', '')} {agent.get('last_name', '')}",
                property=property_data,
                notification_round=notification_round,
                accept_url=f"{base_url}/agent/assignments/{notification_id}/accept?token={secure_token}",
                reject_url=f"{base_url}/agent/assignments/{notification_id}/reject?token={secure_token}"
            )
            
            print(f"[SEQUENTIAL_NOTIFICATION] Sending email to {agent_email} for property {property_data.get('title')}")
            email_result = await send_email(
                to=agent_email,
                subject=f"New Property Assignment: {property_data.get('title', 'Property')} - Round {notification_round}",
                html=email_html
            )
            print(f"[SEQUENTIAL_NOTIFICATION] Email send result: {email_result}")
            
            # Update notification with email status
            await db.update("agent_property_notifications", {
                "email_sent": True,
                "email_sent_at": dt.datetime.utcnow().isoformat(),
                "updated_at": dt.datetime.utcnow().isoformat()
            }, {"id": notification_id})
            
            print(f"[SEQUENTIAL_NOTIFICATION] Sent notification to agent {agent_id} for property {property_id} (Round {notification_round})")
            
            # Start a background task to handle timeout
            # Use ensure_future to ensure it runs in the background without blocking
            asyncio.ensure_future(SequentialAgentNotificationService._handle_timeout(property_id, notification_id))

            return {
                "success": True,
                "notification_id": notification_id,
                "agent_id": agent_id,
                "round": notification_round
            }
            
        except Exception as e:
            print(f"[SEQUENTIAL_NOTIFICATION] Error sending notification: {e}")
            print(traceback.format_exc())
            return {"success": False, "error": str(e)}
    
    @staticmethod
    async def _handle_timeout(property_id: str, notification_id: str):
        """
        Waits 5 minutes and marks the notification as timed out if still pending.
        After timeout, immediately triggers the next agent notification.
        """
        await asyncio.sleep(300) # 5 minutes - Link expires and becomes invalid
        try:
            notification_res = await db.select("agent_property_notifications", filters={"id": notification_id})
            if notification_res and notification_res[0].get("status") == "pending":
                print(f"[TIMEOUT] Notification {notification_id} for property {property_id} timed out after 5 minutes.")
                await db.update("agent_property_notifications", {
                    "status": "timeout",
                    "responded_at": dt.datetime.utcnow().isoformat()
                }, {"id": notification_id})
                
                # Immediately trigger the queue to process the next agent
                # The 5-minute timeout itself acts as the gap between notifications
                print(f"[TIMEOUT] Moving to next agent for property {property_id}...")
                await SequentialAgentNotificationService._process_queue(property_id)
        except Exception as e:
            print(f"[TIMEOUT] Error in _handle_timeout for notification {notification_id}: {e}")
            traceback.print_exc()

    @staticmethod
    async def accept_assignment(notification_id: str, agent_id: str) -> Dict[str, Any]:
        """Agent accepts the property assignment"""
        try:
            # Get notification
            notifications = await db.select("agent_property_notifications",
                filters={"id": notification_id, "agent_id": agent_id})
            
            if not notifications:
                return {"success": False, "error": "Notification not found or not intended for you."}
            
            notification = notifications[0]
            property_id = notification.get("property_id")

            # Check if already expired (using status, as timeout handler updates it)
            if notification.get("status") != "pending":
                return {"success": False, "error": "This assignment link has expired or is no longer available. Links are valid for 5 minutes only."}
            
            # Double-check expiration time
            expires_at_str = notification.get("expires_at")
            if expires_at_str:
                try:
                    expires_at = dt.datetime.fromisoformat(expires_at_str.replace('Z', '+00:00'))
                    now = dt.datetime.utcnow()
                    if now > expires_at:
                        # Mark as expired
                        await db.update("agent_property_notifications", {
                            "status": "expired",
                            "updated_at": dt.datetime.utcnow().isoformat()
                        }, {"id": notification_id})
                        return {"success": False, "error": "This assignment link has expired. Links are valid for 5 minutes only."}
                except Exception as date_error:
                    print(f"[ACCEPT] Error parsing expiration date: {date_error}")
            
            # Final check: ensure property is still unassigned
            prop_res = await db.select("properties", filters={"id": property_id})
            if not prop_res or prop_res[0].get("agent_id"):
                return {"success": False, "error": "This property has already been assigned to another agent."}
            
            # Update notification
            await db.update("agent_property_notifications", {
                "status": "accepted",
                "response": "accept",
                "responded_at": dt.datetime.utcnow().isoformat(),
                "updated_at": dt.datetime.utcnow().isoformat()
            }, {"id": notification_id})
            
            # Assign property to agent
            await db.update("properties", {
                "agent_id": agent_id,
                "assigned_agent_id": agent_id,
                "updated_at": dt.datetime.utcnow().isoformat()
            }, {"id": property_id})
            
            # Complete queue
            await db.update("property_assignment_queue", {
                "status": "completed",
                "assignment_completed": True,
                "final_agent_id": agent_id,
                "completed_at": dt.datetime.utcnow().isoformat(),
                "updated_at": dt.datetime.utcnow().isoformat()
            }, {"property_id": property_id})
            
            # Mark all other pending notifications for this property as cancelled
            # This is important to stop other timeout handlers
            other_notifications = await db.select("agent_property_notifications", filters={
                "property_id": property_id,
                "status": "pending"
            })
            for notif in other_notifications:
                if notif['id'] != notification_id:
                    await db.update("agent_property_notifications", {"status": "cancelled"}, {"id": notif['id']})

            print(f"[SEQUENTIAL_NOTIFICATION] Agent {agent_id} accepted property {property_id}")
            
            # Send email notification to seller about agent assignment
            try:
                property_data = prop_res[0] if prop_res else {}
                owner_id = property_data.get("owner_id") or property_data.get("added_by")
                
                if owner_id:
                    # Get seller details
                    sellers = await db.select("users", filters={"id": owner_id})
                    if sellers:
                        seller = sellers[0]
                        seller_email = seller.get("email")
                        seller_name = f"{seller.get('first_name', '')} {seller.get('last_name', '')}".strip() or "Seller"
                        
                        # Get agent details
                        agents = await db.select("users", filters={"id": agent_id})
                        if agents:
                            agent = agents[0]
                            agent_name = f"{agent.get('first_name', '')} {agent.get('last_name', '')}".strip()
                            agent_email = agent.get("email")
                            agent_phone = agent.get("phone_number", "N/A")
                            
                            # Send email to seller
                            from ..services.email import send_email
                            property_title = property_data.get("title", "your property")
                            
                            email_subject = f"Agent Assigned to Your Property: {property_title}"
                            email_body = f"""
                            <html>
                            <body>
                                <h2>Agent Assigned to Your Property</h2>
                                <p>Dear {seller_name},</p>
                                <p>Great news! An agent has been assigned to your property: <strong>{property_title}</strong></p>
                                
                                <h3>Agent Details:</h3>
                                <ul>
                                    <li><strong>Name:</strong> {agent_name}</li>
                                    <li><strong>Email:</strong> {agent_email}</li>
                                    <li><strong>Phone:</strong> {agent_phone}</li>
                                </ul>
                                
                                <p>You can now contact the agent directly or view their details in your dashboard.</p>
                                
                                <p>Thank you for using Home & Own!</p>
                            </body>
                            </html>
                            """
                            
                            await send_email(
                                to_email=seller_email,
                                subject=email_subject,
                                body=email_body
                            )
                            print(f"[SEQUENTIAL_NOTIFICATION] Email sent to seller {seller_email} about agent assignment")
            except Exception as email_error:
                print(f"[SEQUENTIAL_NOTIFICATION] Error sending email to seller: {email_error}")
                # Don't fail the assignment if email fails
            
            return {
                "success": True,
                "message": "Property assignment accepted",
                "property_id": property_id
            }
            
        except Exception as e:
            print(f"[SEQUENTIAL_NOTIFICATION] Error accepting assignment: {e}")
            print(traceback.format_exc())
            return {"success": False, "error": str(e)}
    
    @staticmethod
    async def reject_assignment(notification_id: str, agent_id: str, reason: Optional[str] = None) -> Dict[str, Any]:
        """Agent rejects the property assignment"""
        try:
            # Get notification
            notifications = await db.select("agent_property_notifications",
                filters={"id": notification_id, "agent_id": agent_id})
            
            if not notifications:
                return {"success": False, "error": "Notification not found"}
            
            notification = notifications[0]
            property_id = notification.get("property_id")
            
            # Check if already responded or expired
            if notification.get("status") != "pending":
                return {"success": False, "error": "This assignment link has already been responded to or has expired. Links are valid for 5 minutes only."}
            
            # Check expiration time
            expires_at_str = notification.get("expires_at")
            if expires_at_str:
                try:
                    expires_at = dt.datetime.fromisoformat(expires_at_str.replace('Z', '+00:00'))
                    now = dt.datetime.utcnow()
                    if now > expires_at:
                        await db.update("agent_property_notifications", {
                            "status": "expired",
                            "updated_at": dt.datetime.utcnow().isoformat()
                        }, {"id": notification_id})
                        return {"success": False, "error": "This assignment link has expired. Links are valid for 5 minutes only."}
                except Exception as date_error:
                    print(f"[REJECT] Error parsing expiration date: {date_error}")
            
            # Update notification
            await db.update("agent_property_notifications", {
                "status": "rejected",
                "response": "reject",
                "rejection_reason": reason or "No reason provided",
                "responded_at": dt.datetime.utcnow().isoformat(),
                "updated_at": dt.datetime.utcnow().isoformat()
            }, {"id": notification_id})
            
            print(f"[SEQUENTIAL_NOTIFICATION] Agent {agent_id} rejected property {property_id}, moving to next agent immediately")

            # Immediately trigger the queue to process the next agent
            # No delay needed - immediate rejection allows faster assignment  
            # Use ensure_future so it doesn't block the response
            asyncio.ensure_future(SequentialAgentNotificationService._process_queue(property_id))
            
            return {
                "success": True,
                "message": "Property assignment rejected, next agent will be notified shortly"
            }
            
        except Exception as e:
            print(f"[SEQUENTIAL_NOTIFICATION] Error rejecting assignment: {e}")
            print(traceback.format_exc())
            return {"success": False, "error": str(e)}
    
    @staticmethod
    async def get_assignment_tracking(property_id: str) -> Dict[str, Any]:
        """Get complete tracking information for admin dashboard"""
        try:
            # Get queue status
            queue = await db.select("property_assignment_queue", filters={"property_id": property_id})
            queue_data = queue[0] if queue else None
            
            # Get all notifications
            notifications = await db.select("agent_property_notifications",
                filters={"property_id": property_id})
            
            # Get agent details for each notification
            notification_details = []
            for notif in notifications:
                agent_id = notif.get("agent_id")
                agent_data = None
                if agent_id:
                    agents = await db.select("users", filters={"id": agent_id})
                    if agents:
                        agent = agents[0]
                        agent_data = {
                            "id": agent_id,
                            "name": f"{agent.get('first_name', '')} {agent.get('last_name', '')}",
                            "email": agent.get("email", "")
                        }
                
                notification_details.append({
                    "id": notif.get("id"),
                    "agent": agent_data,
                    "round": notif.get("notification_round"),
                    "status": notif.get("status"),
                    "sent_at": notif.get("sent_at"),
                    "expires_at": notif.get("expires_at"),
                    "responded_at": notif.get("responded_at"),
                    "response": notif.get("response"),
                    "rejection_reason": notif.get("rejection_reason"),
                    "email_sent": notif.get("email_sent"),
                    "email_sent_at": notif.get("email_sent_at")
                })
            
            return {
                "property_id": property_id,
                "queue_status": queue_data.get("status") if queue_data else None,
                "current_agent_id": queue_data.get("current_agent_id") if queue_data else None,
                "current_round": queue_data.get("current_round") if queue_data else 1,
                "total_notifications_sent": queue_data.get("total_notifications_sent") if queue_data else 0,
                "total_agents_contacted": queue_data.get("total_agents_contacted") if queue_data else 0,
                "assignment_completed": queue_data.get("assignment_completed") if queue_data else False,
                "final_agent_id": queue_data.get("final_agent_id") if queue_data else None,
                "started_at": queue_data.get("started_at") if queue_data else None,
                "completed_at": queue_data.get("completed_at") if queue_data else None,
                "notifications": notification_details,
                "agent_list": queue_data.get("agent_list", []) if queue_data else []
            }
            
        except Exception as e:
            print(f"[SEQUENTIAL_NOTIFICATION] Error getting tracking: {e}")
            print(traceback.format_exc())
            return {"success": False, "error": str(e)}

