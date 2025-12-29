from __future__ import annotations
from typing import Dict, Any

def wrap_html(body_html: str, title: str = "Home & Own Notification") -> str:
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset='utf-8' />
      <meta name='viewport' content='width=device-width, initial-scale=1.0' />
      <title>{title}</title>
      <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background: #f9fafb; color:#111827; margin:0; line-height: 1.6; }}
        .container {{ max-width: 640px; margin: 0 auto; padding: 24px; }}
        .card {{ background:#fff; border-radius:12px; padding: 32px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
        .btn {{ display:inline-block; background:#0ca5e9; color:#fff; padding: 14px 28px; text-decoration:none; border-radius: 8px; font-weight:600; margin: 16px 0; }}
        .btn:hover {{ background: #0891b2; }}
        .muted {{ color:#6b7280; font-size: 14px; }}
        .header {{ text-align: center; margin-bottom: 24px; }}
        .logo {{ font-size: 28px; font-weight: 800; color: #0ca5e9; margin-bottom: 8px; }}
      </style>
    </head>
    <body>
      <div class='container'>
        <div class='card'>
          <div class='header'>
            <div class='logo'>Home & Own</div>
            <div class='muted'>Your Premier Real Estate Platform</div>
          </div>
          {body_html}
          <hr style='margin:32px 0; border:none; border-top:1px solid #e5e7eb;' />
          <div class='muted' style='text-align:center;'>
            <p>This is an automated message from Home & Own.<br/>
            Please do not reply to this email.</p>
            <p style='font-size: 12px; color: #9ca3af;'>© 2025 Home & Own. All rights reserved.</p>
          </div>
        </div>
      </div>
    </body>
    </html>
    """

def verification_email(first_name: str, link: str) -> str:
    body = f"""
      <h2 style='margin-top:0; color: #1e293b;'>Welcome to Home & Own! 🎉</h2>
      <p style='font-size: 16px;'>Hi <strong>{first_name or 'there'}</strong>,</p>
      <p style='font-size: 16px;'>Thank you for joining Home & Own! To complete your registration and access all features, please verify your email address by clicking the button below:</p>
      
      <div style='text-align:center; margin: 32px 0;'>
        <a class='btn' href='{link}'>✨ Verify My Email Address</a>
      </div>
      
      <div style='background-color: #fef3c7; border: 1px solid #f59e0b; border-radius: 8px; padding: 16px; margin: 24px 0;'>
        <p style='margin: 0; font-size: 14px; color: #92400e;'>
          <strong>⏰ Important:</strong> This verification link will expire in 24 hours for security purposes.
        </p>
      </div>
      
      <p class='muted'>If the button doesn't work, copy and paste this link into your browser:</p>
      <p style='word-break:break-all; background: #f3f4f6; padding: 12px; border-radius: 6px; font-family: monospace; font-size: 13px;'>{link}</p>
      
      <p class='muted'>If you didn't create an account with Home & Own, you can safely ignore this email.</p>
    """
    return wrap_html(body, title="Verify your email - Home & Own")

def reset_password_email(first_name: str | None, link: str) -> str:
    body = f"""
      <h2 style='margin-top:0; color: #1e293b;'>Reset Your Password 🔐</h2>
      <p style='font-size: 16px;'>Hi <strong>{first_name or 'there'}</strong>,</p>
      <p style='font-size: 16px;'>You requested to reset your password for your Home & Own account. Click the button below to set a new password:</p>
      
      <div style='text-align:center; margin: 32px 0;'>
        <a class='btn' href='{link}'>🔄 Reset My Password</a>
      </div>
      
      <div style='background-color: #fef3c7; border: 1px solid #f59e0b; border-radius: 8px; padding: 16px; margin: 24px 0;'>
        <p style='margin: 0; font-size: 14px; color: #92400e;'>
          <strong>⏰ Security:</strong> This reset link will expire in 2 hours.
        </p>
      </div>
      
      <p class='muted'>If you did not request this password reset, you can safely ignore this email. Your password will remain unchanged.</p>
    """
    return wrap_html(body, title="Reset your password - Home & Own")

def notify_info(subject: str, lines: list[str]) -> tuple[str, str]:
    body = f"""
      <h2 style='margin-top:0; color: #1e293b;'>📢 System Notification</h2>
      <p style='font-size: 16px;'>A new activity occurred on Home & Own platform:</p>
      <ul style='padding-left: 20px; font-size: 16px;'>
    """
    for ln in lines:
        body += f"<li style='margin: 8px 0;'>{ln}</li>"
    body += """
      </ul>
      <p class='muted'>This is an automated system notification.</p>
    """
    return f"Home & Own - {subject}", wrap_html(body, title=subject)

def inquiry_email(to_owner: bool, customer_name: str, property_details: Dict[str, Any] | None, property_id: str | int, is_owner: bool = False) -> tuple[str, str]:
    property_title = property_details.get("title", f"Property #{property_id}") if property_details else f"Property #{property_id}"
    
    if to_owner:
        if is_owner:
            subject = f"🏠 New inquiry for your property: {property_title}"
            location_html = f'<p><strong>Location:</strong> {property_details.get("city", "")}, {property_details.get("state", "")}</p>' if property_details else ''
            
            # Fix the price display logic to avoid nested f-strings
            if property_details and property_details.get("listing_type") == "SALE":
                price_display = f'₹{property_details.get("price", "N/A")}'
            elif property_details:
                price_display = f'₹{property_details.get("monthly_rent", "N/A")}/month'
            else:
                price_display = "N/A"
            
            price_html = f'<p><strong>Price:</strong> {price_display}</p>' if property_details else ''
            
            body = f"""
              <h2 style='margin-top:0; color: #1e293b;'>New Inquiry for Your Property! 💬</h2>
              <p style='font-size: 16px;'>Hi Property Owner,</p>
              <p style='font-size: 16px;'>You have received a new inquiry from a potential customer for your property:</p>
              
              <div style='background: #f8fafc; border-radius: 8px; padding: 20px; margin: 20px 0;'>
                <p><strong>Customer:</strong> {customer_name}</p>
                <p><strong>Property:</strong> {property_title}</p>
                <p><strong>Property ID:</strong> #{property_id}</p>
                {location_html}
                {price_html}
              </div>
              
              <p style='font-size: 16px;'>Please respond to this inquiry promptly to maintain good customer relationships.</p>
              
              <div style='background: #ecfdf5; border: 1px solid #10b981; border-radius: 8px; padding: 16px; margin: 20px 0;'>
                <p style='margin: 0; color: #065f46; font-size: 14px;'>
                  <strong>💡 Quick Response Tip:</strong> Customers who receive responses within 24 hours are 5x more likely to proceed with the transaction.
                </p>
              </div>
            """
        else:
            subject = f"🏠 New inquiry for {property_title}"
            body = f"""
              <h2 style='margin-top:0; color: #1e293b;'>New Property Inquiry! 💬</h2>
              <p style='font-size: 16px;'>You have received a new inquiry from a potential customer:</p>
              
              <div style='background: #f8fafc; border-radius: 8px; padding: 20px; margin: 20px 0;'>
                <p><strong>Customer:</strong> {customer_name}</p>
                <p><strong>Property:</strong> {property_title}</p>
                <p><strong>Inquiry ID:</strong> #{property_id}</p>
              </div>
              
              <p style='font-size: 16px;'>Please respond to this inquiry as soon as possible to maintain good customer relationships.</p>
              
              <div style='background: #ecfdf5; border: 1px solid #10b981; border-radius: 8px; padding: 16px; margin: 20px 0;'>
                <p style='margin: 0; color: #065f46; font-size: 14px;'>
                  <strong>💡 Quick Response Tip:</strong> Customers who receive responses within 24 hours are 5x more likely to proceed with the transaction.
                </p>
              </div>
            """
    else:
        subject = "✅ Your inquiry was received - Home & Own"
        body = f"""
          <h2 style='margin-top:0; color: #1e293b;'>Thank You for Your Inquiry! 🙏</h2>
          <p style='font-size: 16px;'>Hi <strong>{customer_name}</strong>,</p>
          <p style='font-size: 16px;'>Thank you for your interest in <strong>{property_title}</strong>. We have forwarded your inquiry to the property owner.</p>
          
          <div style='background: #eff6ff; border: 1px solid #3b82f6; border-radius: 8px; padding: 16px; margin: 20px 0;'>
            <p style='margin: 0; color: #1e40af; font-size: 14px;'>
              <strong>📞 What's Next:</strong> The property owner will contact you directly within 24 hours to discuss your requirements and schedule a viewing if needed.
            </p>
          </div>
          
          <p style='font-size: 16px;'>If you have any additional questions, feel free to contact our support team.</p>
        """
    
    return subject, wrap_html(body, title=subject)

def booking_email(to_owner: bool, customer_name: str, property_details: Dict[str, Any] | None, property_id: str | int, time_desc: str | None, is_owner: bool = False) -> tuple[str, str]:
    property_title = property_details.get("title", f"Property #{property_id}") if property_details else f"Property #{property_id}"
    
    if to_owner:
        if is_owner:
            subject = f"🗓️ New tour request for your property: {property_title}"
            body = f"""
              <h2 style='margin-top:0; color: #1e293b;'>New Tour Request for Your Property! 🏠</h2>
              <p style='font-size: 16px;'>Hi Property Owner,</p>
              <p style='font-size: 16px;'>You have received a new tour request for your property:</p>
              
              <div style='background: #f8fafc; border-radius: 8px; padding: 20px; margin: 20px 0;'>
                <p><strong>Customer:</strong> {customer_name}</p>
                <p><strong>Property:</strong> {property_title}</p>
                <p><strong>Property ID:</strong> #{property_id}</p>
                {f'<p><strong>Requested Time:</strong> {time_desc}</p>' if time_desc else ''}
                {f'<p><strong>Location:</strong> {property_details.get("city", "")}, {property_details.get("state", "")}</p>' if property_details else ''}
              </div>
              
              <p style='font-size: 16px;'>Please confirm this tour request with the customer as soon as possible.</p>
              
              <div style='background: #ecfdf5; border: 1px solid #10b981; border-radius: 8px; padding: 16px; margin: 20px 0;'>
                <p style='margin: 0; color: #065f46; font-size: 14px;'>
                  <strong>💡 Tip:</strong> Confirmed tours lead to higher conversion rates. Contact the customer within 24 hours.
                </p>
              </div>
            """
        else:
            subject = f"🗓️ New tour request for {property_title}"
            body = f"""
              <h2 style='margin-top:0; color: #1e293b;'>New Property Tour Request! 🏠</h2>
              <p style='font-size: 16px;'>You have received a new tour request:</p>
              
              <div style='background: #f8fafc; border-radius: 8px; padding: 20px; margin: 20px 0;'>
                <p><strong>Customer:</strong> {customer_name}</p>
                <p><strong>Property:</strong> {property_title}</p>
                {f'<p><strong>Preferred Time:</strong> {time_desc}</p>' if time_desc else ''}
                <p><strong>Booking ID:</strong> #{property_id}</p>
              </div>
              
              <p style='font-size: 16px;'>Please confirm this tour request with the customer as soon as possible.</p>
            """
    else:
        subject = "✅ Tour request submitted - Home & Own"
        body = f"""
          <h2 style='margin-top:0; color: #1e293b;'>Tour Request Submitted! 📅</h2>
          <p style='font-size: 16px;'>Hi <strong>{customer_name}</strong>,</p>
          <p style='font-size: 16px;'>Your tour request for <strong>{property_title}</strong> has been submitted successfully.</p>
          
          <div style='background: #ecfdf5; border: 1px solid #10b981; border-radius: 8px; padding: 16px; margin: 20px 0;'>
            <p style='margin: 0; color: #065f46; font-size: 14px;'>
              <strong>📞 Next Steps:</strong> The property owner will contact you within 24 hours to confirm the tour schedule and provide additional details.
            </p>
          </div>
          
          {f'<p style="font-size: 16px;"><strong>Requested Time:</strong> {time_desc}</p>' if time_desc else ''}
        """
    
    return subject, wrap_html(body, title=subject)

def booking_status_email(booking: Dict[str, Any], property_details: Dict[str, Any] | None, status: str, agent_notes: str | None = None, is_agent: bool = False) -> tuple[str, str]:
    property_title = property_details.get("title", f"Property #{booking.get('property_id')}") if property_details else f"Property #{booking.get('property_id')}"

    status_messages = {
        "confirmed": "✅ Tour Confirmed",
        "cancelled": "❌ Tour Cancelled",
        "completed": "🏁 Tour Completed",
        "pending": "⏳ Tour Status Update"
    }

    status_colors = {
        "confirmed": "#10b981",
        "cancelled": "#ef4444",
        "completed": "#3b82f6",
        "pending": "#f59e0b"
    }

    if is_agent:
        subject = f"Booking Status Update: {property_title}"
        body = f"""
          <h2 style='margin-top:0; color: #1e293b;'>Booking Status Update</h2>
          <p style='font-size: 16px;'>Hi Agent,</p>
          <p style='font-size: 16px;'>A booking status has been updated:</p>

          <div style='background: #f8fafc; border-radius: 8px; padding: 20px; margin: 20px 0;'>
            <p><strong>Property:</strong> {property_title}</p>
            <p><strong>Customer:</strong> {booking.get('name', 'N/A')}</p>
            <p><strong>Email:</strong> {booking.get('email', 'N/A')}</p>
            <p><strong>Phone:</strong> {booking.get('phone', 'N/A')}</p>
            <p><strong>Requested Date:</strong> {booking.get('booking_date', 'N/A')}</p>
            <p><strong>Requested Time:</strong> {booking.get('booking_time', 'N/A')}</p>
            <p><strong>Status:</strong> <span style='color: {status_colors.get(status, '#6b7280')}; font-weight: bold;'>{status.upper()}</span></p>
            {f'<p><strong>Notes:</strong> {agent_notes}</p>' if agent_notes else ''}
          </div>
        """
    else:
        subject = f"{status_messages.get(status, 'Tour Update')}: {property_title}"
        body = f"""
          <h2 style='margin-top:0; color: #1e293b;'>{status_messages.get(status, 'Tour Update')}</h2>
          <p style='font-size: 16px;'>Hi <strong>{booking.get('name', 'there')}</strong>,</p>
          <p style='font-size: 16px;'>Your tour request for <strong>{property_title}</strong> has been {status}.</p>

          <div style='background: #f8fafc; border-radius: 8px; padding: 20px; margin: 20px 0;'>
            <p><strong>Property:</strong> {property_title}</p>
            <p><strong>Requested Date:</strong> {booking.get('booking_date', 'N/A')}</p>
            <p><strong>Requested Time:</strong> {booking.get('booking_time', 'N/A')}</p>
            <p><strong>Status:</strong> <span style='color: {status_colors.get(status, '#6b7280')}; font-weight: bold;'>{status.upper()}</span></p>
            {f'<p><strong>Agent Notes:</strong> {agent_notes}</p>' if agent_notes else ''}
          </div>

          {f'<div style="background: #ecfdf5; border: 1px solid #10b981; border-radius: 8px; padding: 16px; margin: 20px 0;"><p style="margin: 0; color: #065f46; font-size: 14px;"><strong>📞 Next Steps:</strong> Please contact us if you have any questions about this update.</p></div>' if status == 'confirmed' else ''}
          {f'<div style="background: #fef2f2; border: 1px solid #ef4444; border-radius: 8px; padding: 16px; margin: 20px 0;"><p style="margin: 0; color: #991b1b; font-size: 14px;"><strong>⚠️ Cancellation Notice:</strong> Your tour has been cancelled. Please contact us to reschedule.</p></div>' if status == 'cancelled' else ''}
        """

    return subject, wrap_html(body, title=subject)

def inquiry_status_email(inquiry: Dict[str, Any], property_details: Dict[str, Any] | None, status: str, agent_notes: str | None = None, is_agent: bool = False) -> tuple[str, str]:
    property_title = property_details.get("title", f"Property #{inquiry.get('property_id')}") if property_details else f"Property #{inquiry.get('property_id')}"

    status_messages = {
        "new": "📨 New Inquiry Received",
        "contacted": "📞 We've Contacted You",
        "confirmed": "✅ Inquiry Confirmed",
        "cancelled": "❌ Inquiry Cancelled",
        "completed": "🏁 Inquiry Completed"
    }

    status_colors = {
        "new": "#3b82f6",
        "contacted": "#f59e0b",
        "confirmed": "#10b981",
        "cancelled": "#ef4444",
        "completed": "#8b5cf6"
    }

    if is_agent:
        subject = f"Inquiry Status Update: {property_title}"
        body = f"""
          <h2 style='margin-top:0; color: #1e293b;'>Inquiry Status Update</h2>
          <p style='font-size: 16px;'>Hi Agent,</p>
          <p style='font-size: 16px;'>An inquiry status has been updated:</p>

          <div style='background: #f8fafc; border-radius: 8px; padding: 20px; margin: 20px 0;'>
            <p><strong>Property:</strong> {property_title}</p>
            <p><strong>Customer:</strong> {inquiry.get('name', 'N/A')}</p>
            <p><strong>Email:</strong> {inquiry.get('email', 'N/A')}</p>
            <p><strong>Phone:</strong> {inquiry.get('phone', 'N/A')}</p>
            <p><strong>Message:</strong> {inquiry.get('message', 'N/A')}</p>
            <p><strong>Status:</strong> <span style='color: {status_colors.get(status, '#6b7280')}; font-weight: bold;'>{status.upper()}</span></p>
            {f'<p><strong>Notes:</strong> {agent_notes}</p>' if agent_notes else ''}
          </div>
        """
    else:
        subject = f"{status_messages.get(status, 'Inquiry Update')}: {property_title}"
        body = f"""
          <h2 style='margin-top:0; color: #1e293b;'>{status_messages.get(status, 'Inquiry Update')}</h2>
          <p style='font-size: 16px;'>Hi <strong>{inquiry.get('name', 'there')}</strong>,</p>
          <p style='font-size: 16px;'>Your inquiry about <strong>{property_title}</strong> has been {status}.</p>

          <div style='background: #f8fafc; border-radius: 8px; padding: 20px; margin: 20px 0;'>
            <p><strong>Property:</strong> {property_title}</p>
            <p><strong>Your Message:</strong> {inquiry.get('message', 'N/A')}</p>
            <p><strong>Status:</strong> <span style='color: {status_colors.get(status, '#6b7280')}; font-weight: bold;'>{status.upper()}</span></p>
            {f'<p><strong>Agent Notes:</strong> {agent_notes}</p>' if agent_notes else ''}
          </div>

          {f'<div style="background: #ecfdf5; border: 1px solid #10b981; border-radius: 8px; padding: 16px; margin: 20px 0;"><p style="margin: 0; color: #065f46; font-size: 14px;"><strong>📞 Next Steps:</strong> Our agent will contact you soon with more details.</p></div>' if status == 'contacted' else ''}
          {f'<div style="background: #fef2f2; border: 1px solid #ef4444; border-radius: 8px; padding: 16px; margin: 20px 0;"><p style="margin: 0; color: #991b1b; font-size: 14px;"><strong>⚠️ Update:</strong> Your inquiry has been cancelled. Please contact us if you need further assistance.</p></div>' if status == 'cancelled' else ''}
        """

    return subject, wrap_html(body, title=subject)

def inquiry_confirmation_email(inquirer_name: str, property_title: str, property_id: str, message: str) -> str:
    body = f"""
      <h2 style='margin-top:0; color: #1e293b;'>Inquiry Sent Successfully! 📧</h2>
      <p style='font-size: 16px;'>Hi <strong>{inquirer_name}</strong>,</p>
      <p style='font-size: 16px;'>Thank you for your interest in <strong>{property_title}</strong>! Your inquiry has been sent to the property owner.</p>
      
      <div style='background: #f8fafc; padding: 20px; border-radius: 8px; margin: 20px 0;'>
        <h3 style='margin-top:0; color: #1e293b;'>Your Inquiry Details:</h3>
        <p><strong>Property:</strong> {property_title}</p>
        <p><strong>Your Message:</strong> {message}</p>
        <p><strong>Status:</strong> <span style='color: #059669; font-weight: 600;'>Sent to Property Owner</span></p>
      </div>
      
      <p style='font-size: 16px;'>What happens next?</p>
      <ul style='font-size: 16px; color: #374151;'>
        <li>The property owner will review your inquiry</li>
        <li>You'll receive a response within 24-48 hours</li>
        <li>You can track your inquiries in your dashboard</li>
      </ul>
      
      <div style='text-align:center; margin: 32px 0;'>
        <a class='btn' href='https://homeandown.com/my-inquiries'>View My Inquiries</a>
      </div>
      
      <p style='font-size: 16px;'>Thank you for choosing Home & Own!</p>
      <p style='font-size: 16px;'>The Home & Own Team</p>
    """
    return wrap_html(body, "Inquiry Confirmation - Home & Own")

def inquiry_confirmation_email(inquirer_name: str, property_title: str, message: str) -> str:
    """Email template for inquiry confirmation to the person who sent the inquiry"""
    body = f"""
      <h2 style='margin-top:0; color: #1e293b;'>Thank you for your inquiry! 📧</h2>
      <p style='font-size: 16px;'>Hi <strong>{inquirer_name}</strong>,</p>
      <p style='font-size: 16px;'>Thank you for your interest in <strong>{property_title}</strong>!</p>
      
      <div style='background: #f0f9ff; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #0ca5e9;'>
        <h3 style='margin-top:0; color: #1e293b;'>Your Inquiry Details:</h3>
        <p><strong>Property:</strong> {property_title}</p>
        <p><strong>Your Message:</strong> {message}</p>
        <p><strong>Status:</strong> <span style='color: #059669; font-weight: 600;'>Received</span></p>
      </div>
      
      <p style='font-size: 16px;'>What happens next:</p>
      <ul style='font-size: 16px; color: #374151;'>
        <li>Our team will review your inquiry within 24 hours</li>
        <li>The property owner or agent will contact you directly</li>
        <li>You'll receive updates via email</li>
      </ul>
      
      <div style='text-align:center; margin: 32px 0;'>
        <a class='btn' href='https://homeandown.com/my-inquiries'>View My Inquiries</a>
      </div>
      
      <p style='font-size: 16px;'>We look forward to helping you find your perfect home!</p>
      <p style='font-size: 16px;'>The Home & Own Team</p>
    """
    return wrap_html(body, "Inquiry Confirmed - Home & Own")

def inquiry_notification_email(property_owner_name: str, inquirer_name: str, inquirer_email: str, property_title: str, message: str) -> str:
    """Email template for inquiry notification to property owner"""
    body = f"""
      <h2 style='margin-top:0; color: #1e293b;'>New Property Inquiry! 🏠</h2>
      <p style='font-size: 16px;'>Hi <strong>{property_owner_name}</strong>,</p>
      <p style='font-size: 16px;'>You have received a new inquiry for your property <strong>{property_title}</strong>!</p>
      
      <div style='background: #f8fafc; padding: 20px; border-radius: 8px; margin: 20px 0;'>
        <h3 style='margin-top:0; color: #1e293b;'>Inquiry Details:</h3>
        <p><strong>From:</strong> {inquirer_name}</p>
        <p><strong>Email:</strong> {inquirer_email}</p>
        <p><strong>Property:</strong> {property_title}</p>
        <p><strong>Message:</strong> {message}</p>
      </div>
      
      <p style='font-size: 16px;'>Please respond to this inquiry promptly to maintain good customer relations.</p>
      
      <div style='text-align:center; margin: 32px 0;'>
        <a class='btn' href='mailto:{inquirer_email}?subject=Re: Inquiry about {property_title}'>Reply to Inquiry</a>
      </div>
      
      <p style='font-size: 16px;'>Thank you for using Home & Own!</p>
      <p style='font-size: 16px;'>The Home & Own Team</p>
    """
    return wrap_html(body, "New Property Inquiry - Home & Own")

def booking_confirmation_email(booker_name: str, property_title: str, tour_date: str, tour_time: str, booker_phone: str = None) -> str:
    phone_section = f"<p><strong>Your Contact:</strong> {booker_phone}</p>" if booker_phone else ""
    body = f"""
      <h2 style='margin-top:0; color: #1e293b;'>Tour Booking Confirmed! 📅</h2>
      <p style='font-size: 16px;'>Hi <strong>{booker_name}</strong>,</p>
      <p style='font-size: 16px;'>Your property tour has been successfully booked!</p>
      
      <div style='background: #f0f9ff; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #0ca5e9;'>
        <h3 style='margin-top:0; color: #1e293b;'>Tour Details:</h3>
        <p><strong>Property:</strong> {property_title}</p>
        <p><strong>Date:</strong> {tour_date}</p>
        <p><strong>Time:</strong> {tour_time}</p>
        {phone_section}
        <p><strong>Status:</strong> <span style='color: #059669; font-weight: 600;'>Confirmed</span></p>
      </div>
      
      <p style='font-size: 16px;'>Important reminders:</p>
      <ul style='font-size: 16px; color: #374151;'>
        <li>Please arrive 5 minutes before your scheduled time</li>
        <li>Bring a valid ID for verification</li>
        <li>Contact the property owner if you need to reschedule</li>
      </ul>
      
      <div style='text-align:center; margin: 32px 0;'>
        <a class='btn' href='https://homeandown.com/my-bookings'>View My Bookings</a>
      </div>
      
      <p style='font-size: 16px;'>We look forward to helping you find your perfect home!</p>
      <p style='font-size: 16px;'>The Home & Own Team</p>
    """
    return wrap_html(body, "Tour Booking Confirmed - Home & Own")

def booking_notification_email(property_owner_name: str, booker_name: str, booker_email: str, property_title: str, tour_date: str, tour_time: str, booker_phone: str = None) -> str:
    phone_section = f"<p><strong>Phone:</strong> {booker_phone}</p>" if booker_phone else ""
    body = f"""
      <h2 style='margin-top:0; color: #1e293b;'>New Tour Booking! 📅</h2>
      <p style='font-size: 16px;'>Hi <strong>{property_owner_name}</strong>,</p>
      <p style='font-size: 16px;'>You have received a new tour booking for your property <strong>{property_title}</strong>!</p>
      
      <div style='background: #f0f9ff; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #0ca5e9;'>
        <h3 style='margin-top:0; color: #1e293b;'>Booking Details:</h3>
        <p><strong>Booker:</strong> {booker_name}</p>
        <p><strong>Email:</strong> {booker_email}</p>
        {phone_section}
        <p><strong>Property:</strong> {property_title}</p>
        <p><strong>Tour Date:</strong> {tour_date}</p>
        <p><strong>Tour Time:</strong> {tour_time}</p>
      </div>
      
      <p style='font-size: 16px;'>Please prepare for the tour and contact the booker if needed.</p>
      
      <div style='text-align:center; margin: 32px 0;'>
        <a class='btn' href='mailto:{booker_email}?subject=Tour Confirmation for {property_title}'>Contact Booker</a>
      </div>
      
      <p style='font-size: 16px;'>Thank you for using Home & Own!</p>
      <p style='font-size: 16px;'>The Home & Own Team</p>
    """
    return wrap_html(body, "New Tour Booking - Home & Own")

def approval_email(user_name: str, approval_type: str, status: str, admin_notes: str = "") -> str:
    status_colors = {
        'approved': '#059669',
        'rejected': '#dc2626',
        'resubmit': '#d97706'
    }
    
    status_messages = {
        'approved': 'Congratulations! Your request has been approved.',
        'rejected': 'Your request has been rejected.',
        'resubmit': 'Your request needs to be resubmitted with corrections.'
    }
    
    color = status_colors.get(status, '#6b7280')
    
    body = f"""
      <h2 style='margin-top:0; color: #1e293b;'>Request {status.title()} - Home & Own</h2>
      <p style='font-size: 16px;'>Hi <strong>{user_name}</strong>,</p>
      <p style='font-size: 16px;'>{status_messages.get(status, 'Your request has been processed.')}</p>
      
      <div style='background: #f8fafc; padding: 20px; border-radius: 8px; margin: 20px 0;'>
        <h3 style='margin-top:0; color: #1e293b;'>Request Details:</h3>
        <p><strong>Type:</strong> {approval_type.replace('_', ' ').title()}</p>
        <p><strong>Status:</strong> <span style='color: {color}; font-weight: 600;'>{status.title()}</span></p>
        {f'<p><strong>Admin Notes:</strong> {admin_notes}</p>' if admin_notes else ''}
      </div>
      
      {f'<div style="background: #ecfdf5; border: 1px solid #10b981; border-radius: 8px; padding: 16px; margin: 20px 0;"><p style="margin: 0; color: #065f46; font-size: 14px;"><strong>✅ Next Steps:</strong> You can now access all features of your account.</p></div>' if status == 'approved' else ''}
      {f'<div style="background: #fef2f2; border: 1px solid #ef4444; border-radius: 8px; padding: 16px; margin: 20px 0;"><p style="margin: 0; color: #991b1b; font-size: 14px;"><strong>❌ Update:</strong> Please review the admin notes and contact support if needed.</p></div>' if status == 'rejected' else ''}
      {f'<div style="background: #fef3c7; border: 1px solid #f59e0b; border-radius: 8px; padding: 16px; margin: 20px 0;"><p style="margin: 0; color: #92400e; font-size: 14px;"><strong>⚠️ Action Required:</strong> Please resubmit your request with the requested corrections.</p></div>' if status == 'resubmit' else ''}
      
      <div style='text-align:center; margin: 32px 0;'>
        <a class='btn' href='https://homeandown.com/login'>Access Your Account</a>
      </div>
      
      <p style='font-size: 16px;'>Thank you for using Home & Own!</p>
      <p style='font-size: 16px;'>The Home & Own Team</p>
    """
    return wrap_html(body, f"Request {status.title()} - Home & Own")

def agent_inquiry_assignment_email(agent_name: str, inquirer_name: str, property_title: str, inquiry_message: str) -> str:
    body = f"""
      <h2 style='margin-top:0; color: #1e293b;'>New Inquiry Assignment! 🏠</h2>
      <p style='font-size: 16px;'>Hi <strong>{agent_name}</strong>,</p>
      <p style='font-size: 16px;'>You have been assigned a new inquiry for <strong>{property_title}</strong>!</p>
      
      <div style='background: #f0f9ff; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #0ca5e9;'>
        <h3 style='margin-top:0; color: #1e293b;'>Inquiry Details:</h3>
        <p><strong>From:</strong> {inquirer_name}</p>
        <p><strong>Property:</strong> {property_title}</p>
        <p><strong>Message:</strong> {inquiry_message}</p>
      </div>
      
      <p style='font-size: 16px;'>Please review this inquiry and contact the potential client to schedule a property visit.</p>
      
      <div style='text-align:center; margin: 32px 0;'>
        <a class='btn' href='https://homeandown.com/agent/dashboard'>View Assignment</a>
      </div>
      
      <p style='font-size: 16px;'>Thank you for your service!</p>
      <p style='font-size: 16px;'>The Home & Own Team</p>
    """
    return wrap_html(body, "New Inquiry Assignment - Home & Own")

def agent_inquiry_response_email(inquirer_name: str, agent_name: str, property_title: str, response_message: str, visit_scheduled: bool = False) -> str:
    body = f"""
      <h2 style='margin-top:0; color: #1e293b;'>Agent Response to Your Inquiry! 👨‍💼</h2>
      <p style='font-size: 16px;'>Hi <strong>{inquirer_name}</strong>,</p>
      <p style='font-size: 16px;'>Your assigned agent <strong>{agent_name}</strong> has responded to your inquiry about <strong>{property_title}</strong>!</p>
      
      <div style='background: #f0f9ff; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #0ca5e9;'>
        <h3 style='margin-top:0; color: #1e293b;'>Agent Response:</h3>
        <p><strong>Agent:</strong> {agent_name}</p>
        <p><strong>Property:</strong> {property_title}</p>
        <p><strong>Message:</strong> {response_message}</p>
        {f'<p><strong>Property Visit:</strong> <span style="color: #059669; font-weight: 600;">Scheduled</span></p>' if visit_scheduled else ''}
      </div>
      
      {f'<div style="background: #ecfdf5; border: 1px solid #10b981; border-radius: 8px; padding: 16px; margin: 20px 0;"><p style="margin: 0; color: #065f46; font-size: 14px;"><strong>📅 Next Steps:</strong> Your agent will contact you soon to confirm the property visit details.</p></div>' if visit_scheduled else ''}
      
      <div style='text-align:center; margin: 32px 0;'>
        <a class='btn' href='https://homeandown.com/my-inquiries'>View My Inquiries</a>
      </div>
      
      <p style='font-size: 16px;'>Thank you for choosing Home & Own!</p>
      <p style='font-size: 16px;'>The Home & Own Team</p>
    """
    return wrap_html(body, "Agent Response - Home & Own")

async def get_property_assignment_email(agent_name: str, property: Dict[str, Any], notification_round: int, accept_url: str, reject_url: str) -> str:
    """Generate email template for property assignment notification to agent"""
    
    property_title = property.get('title', 'Untitled Property')
    property_type = property.get('property_type', 'Property')
    listing_type = property.get('listing_type', 'SALE')
    location = f"{property.get('city', '')}, {property.get('state', '')}".strip(', ')
    zip_code = property.get('zip_code', 'N/A')
    
    # Price display
    if listing_type == 'SALE':
        price = f"₹{property.get('price', 0):,.0f}" if property.get('price') else "Price on request"
        price_text = f"<p><strong>Sale Price:</strong> {price}</p>"
    else:
        rent = f"₹{property.get('monthly_rent', 0):,.0f}/month" if property.get('monthly_rent') else "Rent on request"
        price_text = f"<p><strong>Monthly Rent:</strong> {rent}</p>"
    
    # Property details
    bedrooms = property.get('bedrooms', 'N/A')
    bathrooms = property.get('bathrooms', 'N/A')
    area = property.get('area_sqft', 'N/A')
    
    expires_in = "5 minutes"
    
    body = f"""
      <h2 style='margin-top:0; color: #1e293b;'>New Property Assignment Opportunity! 🏠</h2>
      <p style='font-size: 16px;'>Hi <strong>{agent_name}</strong>,</p>
      <p style='font-size: 16px;'>A new property in your area is available for assignment. This is <strong>Round {notification_round}</strong> of notifications.</p>
      
      <div style='background: #f0f9ff; padding: 24px; border-radius: 8px; margin: 24px 0; border-left: 4px solid #0ca5e9;'>
        <h3 style='margin-top:0; color: #1e293b;'>Property Details:</h3>
        <p><strong>Title:</strong> {property_title}</p>
        <p><strong>Type:</strong> {property_type.replace('_', ' ').title()}</p>
        <p><strong>Listing Type:</strong> {listing_type}</p>
        <p><strong>Location:</strong> {location}</p>
        <p><strong>Zipcode:</strong> {zip_code}</p>
        {price_text}
        <p><strong>Bedrooms:</strong> {bedrooms}</p>
        <p><strong>Bathrooms:</strong> {bathrooms}</p>
        <p><strong>Area:</strong> {area} sqft</p>
      </div>
      
      <div style='background: #fef3c7; border: 1px solid #f59e0b; border-radius: 8px; padding: 16px; margin: 24px 0;'>
        <p style='margin: 0; color: #92400e; font-size: 14px; font-weight: 600;'>
          ⏰ <strong>Time Sensitive:</strong> You have <strong>{expires_in}</strong> to accept this assignment. If you don't respond, it will automatically move to the next agent.
        </p>
      </div>
      
      <div style='text-align:center; margin: 32px 0;'>
        <div style='display: inline-block; margin: 0 8px;'>
          <a class='btn' href='{accept_url}' style='background: #10b981; margin-right: 8px;'>✅ Accept Assignment</a>
        </div>
        <div style='display: inline-block; margin: 0 8px;'>
          <a href='{reject_url}' style='display:inline-block; background:#ef4444; color:#fff; padding: 14px 28px; text-decoration:none; border-radius: 8px; font-weight:600;'>❌ Reject</a>
        </div>
      </div>
      
      <div style='background: #ecfdf5; border: 1px solid #10b981; border-radius: 8px; padding: 16px; margin: 20px 0;'>
        <p style='margin: 0; color: #065f46; font-size: 14px;'>
          <strong>💡 What happens when you accept:</strong>
          <ul style='margin: 8px 0 0 20px; padding-left: 0;'>
            <li>You'll be assigned as the primary agent for this property</li>
            <li>All inquiries and bookings will be directed to you</li>
            <li>You'll receive full commission on successful transactions</li>
            <li>You can manage property details and communicate with clients</li>
          </ul>
        </p>
      </div>
      
      <p style='font-size: 16px;'>If the buttons above don't work, you can also access your dashboard:</p>
      <div style='text-align:center; margin: 24px 0;'>
        <a class='btn' href='https://homeandown.com/agent/dashboard'>Go to Agent Dashboard</a>
      </div>
      
      <p style='font-size: 16px;'>Thank you for being part of the Home & Own team!</p>
      <p style='font-size: 16px;'>The Home & Own Team</p>
    """
    return wrap_html(body, f"Property Assignment - Round {notification_round} - Home & Own")