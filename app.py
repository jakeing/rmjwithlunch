"""
RMJ Work Order Management System
A Flask application for managing work orders, time tracking, and project management.
"""

# =============================================================================
# IMPORTS AND DEPENDENCIES
# =============================================================================
import os
from datetime import datetime, timedelta, time as time_class, date
import time
from io import BytesIO
from functools import wraps
import json

# Flask and extensions
from flask import (
    Flask, render_template, request, redirect, url_for, send_from_directory,
    send_file, session, jsonify, flash
)
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message
from flask_migrate import Migrate
import pandas as pd

# Utilities
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

from functools import wraps
import time
from collections import defaultdict

# =============================================================================
# APP CONFIGURATION
# =============================================================================
app = Flask(__name__)

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///workorders.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Security configuration
app.config['SECRET_KEY'] = 'mysecret'
app.config['DELETE_PASSWORD'] = 'secret123'  # Password required for deleting work orders

# File uploads configuration
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'uploads')

# Email configuration
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'rmj.dashboard@gmail.com'
app.config['MAIL_PASSWORD'] = 'ypwl msgw bwoq qhuk'
app.config['MAIL_DEFAULT_SENDER'] = 'rmj.dashboard@gmail.com'

# Notification configuration
app.config['REPORT_NOTIFICATION_ENABLED'] = True
app.config['REPORT_NOTIFICATION_EMAIL'] = 'beverlyn@rmj-consulting.com'
app.config['REPORT_NOTIFICATION_KEYWORDS'] = ['report', 'assessment']

# Initialize extensions
db = SQLAlchemy(app)
mail = Mail(app)
migrate = Migrate(app, db)


# =============================================================================
# DATABASE MODELS
# =============================================================================
class User(db.Model):
    """User model for authentication and access control"""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='user')
    full_name = db.Column(db.String(100), nullable=True)
    
    def set_password(self, password):
        """Set the password hash from plain text password"""
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        """Check if password matches the hash"""
        return check_password_hash(self.password_hash, password)


class WorkOrder(db.Model):
    """Work order model to track jobs and assignments"""
    id = db.Column(db.Integer, primary_key=True)
    customer_work_order_number = db.Column(db.String(50), nullable=True)
    rmj_job_number = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(200), nullable=False)
    status = db.Column(db.String(50))
    owner = db.Column(db.String(50))
    estimated_hours = db.Column(db.Float, nullable=True, default=0)
    priority = db.Column(db.String(20))
    location = db.Column(db.String(100))
    scheduled_date = db.Column(db.Date)
    requested_by = db.Column(db.String(80), nullable=True)
    classification = db.Column(db.String(50), default='Billable')
    approved_for_work = db.Column(db.Boolean, default=False, nullable=False)
    
    # Relationships
    time_entries = db.relationship('TimeEntry', backref='work_order', lazy=True, cascade="all, delete")
    documents = db.relationship('WorkOrderDocument', backref='work_order', lazy=True, cascade="all, delete")

    @property
    def hours_logged(self):
        """Calculate total hours logged for this work order"""
        return sum(entry.hours_worked for entry in self.time_entries)

    @property
    def hours_remaining(self):
        """Calculate remaining hours based on estimate"""
        try:
            estimated = float(self.estimated_hours)
        except (TypeError, ValueError):
            estimated = 0.0
        return estimated - self.hours_logged

    @property
    def has_report(self):
        """Check if this work order has any report documents"""
        for doc in self.documents:
             if doc.document_type == 'report' or "report" in doc.original_filename.lower():
                return True
        return False
    
    @property
    def has_approved_report(self):
        """Check if this work order has any approved report documents"""
        for doc in self.documents:
            if "report" in doc.original_filename.lower() and doc.is_approved:
                return True
        return False


class TimeEntry(db.Model):
    """Time tracking entries for work orders"""
    id = db.Column(db.Integer, primary_key=True)
    work_order_id = db.Column(db.Integer, db.ForeignKey('work_order.id'), nullable=False)
    task_id = db.Column(db.Integer, db.ForeignKey('project_task.id', name='fk_time_entry_task'), nullable=True)
    engineer = db.Column(db.String(50), nullable=False)
    work_date = db.Column(db.Date, nullable=False)
    time_in = db.Column(db.Time, nullable=False)
    time_out = db.Column(db.Time, nullable=False)
    hours_worked = db.Column(db.Float, nullable=False)
    lunch_deduction = db.Column(db.Float, default=0)
    lunch_start = db.Column(db.Time, nullable=True)
    lunch_end = db.Column(db.Time, nullable=True)
    description = db.Column(db.String(200))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    entered_on_jl = db.Column(db.Boolean, default=False)
    entered_on_jt = db.Column(db.Boolean, default=False)
    
    # Relationships
    task = db.relationship('ProjectTask', backref='time_entries', foreign_keys=[task_id])


class WorkOrderDocument(db.Model):
    """Document attachments for work orders"""
    id = db.Column(db.Integer, primary_key=True)
    work_order_id = db.Column(db.Integer, db.ForeignKey('work_order.id'), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=True)
    filename = db.Column(db.String(100), nullable=False)
    original_filename = db.Column(db.String(100))
    upload_time = db.Column(db.DateTime, default=datetime.utcnow)
    is_approved = db.Column(db.Boolean, default=False)
    document_type = db.Column(db.String(50), default='regular')
    
    # Relationships
    project = db.relationship('Project', backref='documents', foreign_keys=[project_id])


class ChangeLog(db.Model):
    """Audit log for tracking all changes in the system"""
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    user_id = db.Column(db.Integer, nullable=True)  # The user who performed the action
    action = db.Column(db.String(255), nullable=False)  # e.g. "Created WorkOrder"
    object_type = db.Column(db.String(50), nullable=False)  # e.g. "WorkOrder", "TimeEntry"
    object_id = db.Column(db.Integer, nullable=True)  # The id of the affected object
    description = db.Column(db.Text, nullable=True)  # More detailed info


class Project(db.Model):
    """Project management for work orders"""
    id = db.Column(db.Integer, primary_key=True)
    work_order_id = db.Column(db.Integer, db.ForeignKey('work_order.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    status = db.Column(db.String(50), default='Planning')  # Planning, In Progress, Completed, On Hold
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    tasks = db.relationship('ProjectTask', backref='project', lazy=True, cascade="all, delete")
    work_order = db.relationship('WorkOrder', backref='project', uselist=False)


class ProjectTask(db.Model):
    """Tasks within a project"""
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    status = db.Column(db.String(50), default='Not Started')  # Not Started, In Progress, Completed, Delayed
    estimated_hours = db.Column(db.Float, default=0)
    actual_hours = db.Column(db.Float, default=0)
    priority = db.Column(db.String(20), default='Medium')  # Low, Medium, High
    dependencies = db.Column(db.String(200))  # Comma-separated list of task IDs this task depends on
    assigned_to = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    position = db.Column(db.Integer, default=0)
    progress_percent = db.Column(db.Integer, nullable=True)  # Manually set progress (0-100)
    
    @property
    def hours_remaining(self):
        """Calculate remaining hours for this task"""
        return self.estimated_hours - self.actual_hours
        
    @property
    def completion_percentage(self):
        """Calculate the task completion percentage"""
        if self.status == 'Completed':
            return 100
        elif self.progress_percent is not None:
            return self.progress_percent  # Return manually set progress if available
        elif self.estimated_hours == 0:
            return 0
        else:
            percentage = (self.actual_hours / self.estimated_hours) * 100
            return min(int(percentage), 99)  # Cap at 99% until marked complete
    
    @property
    def dependent_tasks(self):
        """Get list of tasks this task depends on"""
        if not self.dependencies:
            return []
        task_ids = [int(id.strip()) for id in self.dependencies.split(',') if id.strip().isdigit()]
        return ProjectTask.query.filter(ProjectTask.id.in_(task_ids)).all()
    
    @property
    def actual_hours_from_entries(self):
        """Calculate actual hours from linked time entries"""
        return sum(entry.hours_worked for entry in self.time_entries)
        
    def update_actual_hours(self):
        """Update actual_hours based on linked time entries"""
        self.actual_hours = self.actual_hours_from_entries
        return self.actual_hours

# Add these to the DATABASE MODELS section in app.py

class NotificationSetting(db.Model):
    """Settings for email notifications"""
    id = db.Column(db.Integer, primary_key=True)
    notification_type = db.Column(db.String(50), nullable=False, unique=True)
    enabled = db.Column(db.Boolean, default=False)
    options = db.Column(db.JSON, default={})  # Store type-specific settings
    
    # Relationships
    recipients = db.relationship('NotificationRecipient', backref='notification_setting', 
                                cascade="all, delete-orphan")

class NotificationRecipient(db.Model):
    """Recipients for different notification types"""
    id = db.Column(db.Integer, primary_key=True)
    notification_setting_id = db.Column(db.Integer, db.ForeignKey('notification_setting.id'), 
                                      nullable=False)
    email = db.Column(db.String(100), nullable=False)

# =============================================================================
# AUTHENTICATION DECORATORS
# =============================================================================
def login_required(f):
    """Decorator to require login for routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
         if 'user_id' not in session:
             return redirect(url_for('login'))
         return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """Decorator to require admin privileges for routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        user = User.query.get(session['user_id'])
        print(f"User check: {user.username}, Role: {user.role}")  # Debug logging
        if not user or (user.role.lower() != 'admin' and user.username.lower() != 'admin'):
            return "Access denied", 403
        return f(*args, **kwargs)
    return decorated_function

# Rate limiting decorator
def rate_limit(max_calls=10, time_window=60):
    """Rate limit decorator to prevent too many requests"""
    def decorator(f):
        # Store request counts per user
        request_counts = defaultdict(list)
        
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                return jsonify({'success': False, 'message': 'Authentication required'}), 401
            
            user_id = session['user_id']
            now = time.time()
            
            # Clean up old requests outside the time window
            request_counts[user_id] = [
                req_time for req_time in request_counts[user_id] 
                if now - req_time < time_window
            ]
            
            # Check if rate limit exceeded
            if len(request_counts[user_id]) >= max_calls:
                return jsonify({
                    'success': False, 
                    'message': f'Rate limit exceeded. Maximum {max_calls} requests per {time_window} seconds.'
                }), 429
            
            # Record this request
            request_counts[user_id].append(now)
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================
def populate_user_full_names():
    """Populate full_name for existing users based on mapping"""
    # Keep the existing mapping for migration
    USER_MAPPING = {
        "CHinkle": "Curtis Hinkle",
        "RHinkle": "Ron Hinkle",
        "ASeymour": "Andrew Seymour",
        "AAviles": "Alex Aviles",
        "AYork": "Austin York",
        "MWestmoreland": "Micky Westmoreland",
        "BNewton": "Beverly Newton",
        "BParis": "Benjamin Paris"
    }
    
    # Update existing users
    for username, full_name in USER_MAPPING.items():
        user = User.query.filter_by(username=username).first()
        if user and not user.full_name:
            user.full_name = full_name
    
    db.session.commit()
    print("Updated full names for existing users")


def get_engineer_name(username):
    """Get the full name of an engineer from their username"""
    user = User.query.filter_by(username=username).first()
    if user and user.full_name:
        return user.full_name
    # If no mapping found, just return the username as is
    return username


def parse_date(date_str):
    """Parse a date string into a date object"""
    try:
        return datetime.strptime(date_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return None


def parse_time(time_str):
    """Parse a time string into a time object"""
    try:
        return datetime.strptime(time_str, '%H:%M').time()
    except (ValueError, TypeError):
        return None


def calculate_hours(date_obj, time_in, time_out):
    """Calculate hours worked between time_in and time_out"""
    dt_time_in = datetime.combine(date_obj, time_in)
    dt_time_out = datetime.combine(date_obj, time_out)
    if dt_time_out < dt_time_in:
        dt_time_out += timedelta(days=1)
    return (dt_time_out - dt_time_in).total_seconds() / 3600.0

def calculate_lunch_overlap(work_date, time_in, time_out, lunch_start, lunch_end):
    """Calculate overlap between work time and lunch time"""
    if not lunch_start or not lunch_end:
        return 0.0
    
    # Create datetime objects for comparison
    work_start = datetime.combine(work_date, time_in)
    work_end = datetime.combine(work_date, time_out)
    lunch_start_dt = datetime.combine(work_date, lunch_start)
    lunch_end_dt = datetime.combine(work_date, lunch_end)
    
    # Handle overnight shifts
    if work_end < work_start:
        work_end += timedelta(days=1)
    if lunch_end_dt < lunch_start_dt:
        lunch_end_dt += timedelta(days=1)
    
    # Calculate overlap
    overlap_start = max(work_start, lunch_start_dt)
    overlap_end = min(work_end, lunch_end_dt)
    
    # If there's no overlap, return 0
    if overlap_start >= overlap_end:
        return 0.0
    
    # Return overlap in hours
    return (overlap_end - overlap_start).total_seconds() / 3600.0

def calculate_cross_entry_lunch(work_order_id, engineer, work_date, time_in, time_out, exclude_entry_id=None):
    """Check if other time entries on the same day (ANY work order) have lunch that overlaps with this work time"""
    # Get all other time entries for this engineer on this date (across ALL work orders)
    query = TimeEntry.query.filter_by(
        engineer=engineer,
        work_date=work_date
    )
    
    # Exclude the current entry if editing
    if exclude_entry_id:
        query = query.filter(TimeEntry.id != exclude_entry_id)
    
    other_entries = query.all()
    
    total_lunch_overlap = 0.0
    
    # Check each other entry's lunch time for overlap with this work time
    for entry in other_entries:
        if entry.lunch_start and entry.lunch_end:
            overlap = calculate_lunch_overlap(work_date, time_in, time_out, entry.lunch_start, entry.lunch_end)
            total_lunch_overlap += overlap
    
    return total_lunch_overlap

def check_time_overlap(work_order_id, engineer, work_date, time_in, time_out, exclude_entry_id=None):
    """Check if this time entry overlaps with any existing entries for the same engineer on the same date (across ALL work orders)"""
    # Get all other time entries for this engineer on this date (across ALL work orders)
    query = TimeEntry.query.filter_by(
        engineer=engineer,
        work_date=work_date
    )
    
    # Exclude the current entry if editing
    if exclude_entry_id:
        query = query.filter(TimeEntry.id != exclude_entry_id)
    
    existing_entries = query.all()
    
    # Create datetime objects for the new entry
    new_start = datetime.combine(work_date, time_in)
    new_end = datetime.combine(work_date, time_out)
    
    # Handle overnight shifts
    if new_end < new_start:
        new_end += timedelta(days=1)
    
    # Check each existing entry for overlap
    for entry in existing_entries:
        existing_start = datetime.combine(work_date, entry.time_in)
        existing_end = datetime.combine(work_date, entry.time_out)
        
        # Handle overnight shifts
        if existing_end < existing_start:
            existing_end += timedelta(days=1)
        
        # Check for overlap: entries overlap if start1 < end2 AND end1 > start2
        if new_start < existing_end and new_end > existing_start:
            work_order_info = f" (Work Order: {entry.work_order.rmj_job_number})" if entry.work_order else ""
            return {
                'overlap': True,
                'message': f"Time overlap detected! This entry ({time_in.strftime('%H:%M')} - {time_out.strftime('%H:%M')}) overlaps with an existing entry ({entry.time_in.strftime('%H:%M')} - {entry.time_out.strftime('%H:%M')}) on {work_date.strftime('%Y-%m-%d')}{work_order_info}."
            }
    
    return {'overlap': False}

def validate_lunch_timing(time_in, lunch_end):
    """Validate that lunch is taken within 6 hours of start time"""
    if not lunch_end:
        return {'valid': True}
    
    # Create a reference date for comparison
    ref_date = date.today()
    start_dt = datetime.combine(ref_date, time_in)
    lunch_end_dt = datetime.combine(ref_date, lunch_end)
    
    # Handle overnight shifts
    if lunch_end_dt < start_dt:
        lunch_end_dt += timedelta(days=1)
    
    # Calculate hours between start and lunch end
    hours_diff = (lunch_end_dt - start_dt).total_seconds() / 3600.0
    
    if hours_diff > 6.0:
        return {
            'valid': False,
            'message': f"Lunch must be taken within 6 hours of start time. Your lunch ends {hours_diff:.1f} hours after your start time."
        }
    
    return {'valid': True}

def get_week_dates(year, week):
    """Get the start and end dates for a week"""
    try:
        # Calculate the first Sunday of the week
        start_date = (datetime.fromisocalendar(year, week, 1) - timedelta(days=1)).date()
        end_date = start_date + timedelta(days=6)
        return start_date, end_date
    except Exception:
        return None, None


def log_change(user_id, action, object_type, object_id=None, description=""):
    """Log a change to the database"""
    log_entry = ChangeLog(
        user_id=user_id,
        action=action,
        object_type=object_type,
        object_id=object_id,
        description=description
    )
    db.session.add(log_entry)


def get_sorted_work_orders(status, sort_by='id', order='asc'):
    """Get work orders with the given status, sorted by the given column"""
    valid_sort_columns = {
        'id': WorkOrder.id,
        'customer_work_order_number': WorkOrder.customer_work_order_number,
        'rmj_job_number': WorkOrder.rmj_job_number,
        'description': WorkOrder.description,
        'status': WorkOrder.status,
        'owner': WorkOrder.owner,
        'estimated_hours': WorkOrder.estimated_hours,
        'priority': WorkOrder.priority,
        'location': WorkOrder.location,
        'scheduled_date': WorkOrder.scheduled_date,
        'approved_for_work': WorkOrder.approved_for_work
    }
    sort_column = valid_sort_columns.get(sort_by, WorkOrder.id)
    sort_column = sort_column.desc() if order == 'desc' else sort_column.asc()
    return WorkOrder.query.filter_by(status=status).order_by(sort_column).all()


def is_report_file(filename):
    """Check if a filename contains any of the report keywords."""
    lower_filename = filename.lower()
    return any(keyword in lower_filename for keyword in app.config['REPORT_NOTIFICATION_KEYWORDS'])


def send_report_notification(work_order, document):
    """Send an email notification when a report is uploaded."""
    try:
        recipient = app.config['REPORT_NOTIFICATION_EMAIL']
        subject = f"Report Uploaded for Work Order {work_order.rmj_job_number}"
        
        body = f"""
        A new report has been uploaded for Work Order:
        
        RMJ Job Number: {work_order.rmj_job_number}
        Customer Work Order Number: {work_order.customer_work_order_number}
        Description: {work_order.description}
        
        Document: {document.original_filename}
        Uploaded at: {document.upload_time.strftime('%Y-%m-%d %H:%M:%S')}
        
        You can view the work order details at: {url_for('work_order_detail', work_order_id=work_order.id, _external=True)}
        """
        
        msg = Message(subject=subject, recipients=[recipient], body=body, sender=app.config['MAIL_DEFAULT_SENDER'])
        msg.extra_headers = {
            'X-Priority': '1',
            'X-MSMail-Priority': 'High',
            'Importance': 'High',
            'X-Auto-Response-Suppress': 'OOF, DR, RN, NRN, AutoReply'
        }
        mail.send(msg)
        
        # Log the notification
        log_change(None, "Sent Report Notification", "Email", None, 
                  f"Sent notification for report upload on Work Order #{work_order.id}")
        return True
    except Exception as e:
        # Log the error but don't crash the application
        print(f"Error sending email notification: {e}")
        log_change(None, "Failed Report Notification", "Error", None, 
                  f"Failed to send notification for report upload: {str(e)}")
        return False

# Add these to the HELPER FUNCTIONS section

def get_notification_setting(notification_type):
    """Get notification settings for a given type"""
    setting = NotificationSetting.query.filter_by(notification_type=notification_type).first()
    if setting and setting.enabled:
        return setting
    return None

def get_notification_recipients(setting, work_order=None):
    """Get list of recipients for a notification"""
    recipients = []
    
    # Add all configured recipients for this notification type
    if setting and setting.recipients:
        recipients = [r.email for r in setting.recipients]
    
    # If no recipients, use the default email
    if not recipients:
        default_email = app.config.get('REPORT_NOTIFICATION_EMAIL')
        if default_email:
            recipients.append(default_email)
    
    # Add work order owner if option is enabled and owner has email
    if work_order and setting:
        options = setting.options
        if (notification_type == 'hours_threshold' and options.get('include_work_order_owner')) or \
           (notification_type == 'scheduled_date' and options.get('include_owner')):
            owner = work_order.owner
            if owner and '@' in owner:  # Simple check if owner field contains an email
                if owner not in recipients:
                    recipients.append(owner)
    
    return recipients

def send_report_notification(work_order, document):
    """Send an email notification when a report is uploaded."""
    setting = get_notification_setting('report_upload')
    if not setting:
        return False
    
    try:
        recipients = get_notification_recipients(setting)
        if not recipients:
            return False
        
        subject = f"Report Uploaded for Work Order {work_order.rmj_job_number}"
        
        body = f"""
        A new report has been uploaded for Work Order:
        
        RMJ Job Number: {work_order.rmj_job_number}
        Customer Work Order Number: {work_order.customer_work_order_number}
        Description: {work_order.description}
        
        Document: {document.original_filename}
        Uploaded at: {document.upload_time.strftime('%Y-%m-%d %H:%M:%S')}
        
        You can view the work order details at: {url_for('work_order_detail', work_order_id=work_order.id, _external=True)}
        """
        
        msg = Message(subject=subject, recipients=recipients, body=body, sender=app.config['MAIL_DEFAULT_SENDER'])
        mail.send(msg)
        
        # Log the notification
        log_change(None, "Sent Report Notification", "Email", None, 
                  f"Sent notification for report upload on Work Order #{work_order.id}")
        return True
    except Exception as e:
        print(f"Error sending email notification: {e}")
        log_change(None, "Failed Report Notification", "Error", None, 
                  f"Failed to send notification for report upload: {str(e)}")
        return False

def send_report_approval_notification(work_order, document):
    """Send notification when a report needs approval"""
    setting = get_notification_setting('report_approval')
    if not setting:
        return False
    
    try:
        recipients = get_notification_recipients(setting)
        if not recipients:
            return False
        
        subject = f"Report Requires Approval - Work Order {work_order.rmj_job_number}"
        
        body = f"""
        A report has been uploaded that requires approval:
        
        RMJ Job Number: {work_order.rmj_job_number}
        Customer Work Order Number: {work_order.customer_work_order_number}
        Description: {work_order.description}
        
        Document: {document.original_filename}
        Uploaded at: {document.upload_time.strftime('%Y-%m-%d %H:%M:%S')}
        
        You can view and approve this report at: {url_for('work_order_detail', work_order_id=work_order.id, _external=True)}
        """
        
        msg = Message(subject=subject, recipients=recipients, body=body, sender=app.config['MAIL_DEFAULT_SENDER'])
        mail.send(msg)
        
        log_change(None, "Sent Report Approval Notification", "Email", None, 
                  f"Sent approval notification for report on Work Order #{work_order.id}")
        return True
    except Exception as e:
        print(f"Error sending approval notification: {e}")
        return False

def send_status_change_notification(work_order, old_status, new_status):
    """Send notification when a work order status changes"""
    setting = get_notification_setting('status_change')
    if not setting:
        return False
    
    # Check if this status change should trigger a notification
    options = setting.options
    should_notify = False
    
    if old_status == 'Open' and new_status == 'Complete' and options.get('open_to_complete'):
        should_notify = True
    elif old_status == 'Complete' and new_status == 'Closed' and options.get('complete_to_closed'):
        should_notify = True
    elif new_status == 'Open' and options.get('any_to_open'):
        should_notify = True
        
    if not should_notify:
        return False
    
    try:
        recipients = get_notification_recipients(setting)
        if not recipients:
            return False
        
        subject = f"Work Order Status Changed - {work_order.rmj_job_number}"
        
        body = f"""
        A work order status has been changed:
        
        RMJ Job Number: {work_order.rmj_job_number}
        Customer Work Order Number: {work_order.customer_work_order_number}
        Description: {work_order.description}
        
        Previous Status: {old_status}
        New Status: {new_status}
        
        You can view the work order at: {url_for('work_order_detail', work_order_id=work_order.id, _external=True)}
        """
        
        msg = Message(subject=subject, recipients=recipients, body=body, sender=app.config['MAIL_DEFAULT_SENDER'])
        mail.send(msg)
        
        log_change(None, "Sent Status Change Notification", "Email", None, 
                  f"Sent notification for status change on Work Order #{work_order.id}")
        return True
    except Exception as e:
        print(f"Error sending status change notification: {e}")
        return False

def send_hours_threshold_notification(work_order, hours_logged, estimated_hours, percentage):
    """Send notification when hours threshold is reached"""
    setting = get_notification_setting('hours_threshold')
    if not setting:
        return False
    
    options = setting.options
    warning_threshold = options.get('warning_threshold', 80)
    exceeded_alert = options.get('exceeded_alert', True)
    
    # Check if we should send a notification
    should_notify = False
    notification_type = ""
    
    if percentage >= warning_threshold and percentage < 100:
        should_notify = True
        notification_type = "Warning"
    elif percentage >= 100 and exceeded_alert:
        should_notify = True
        notification_type = "Exceeded"
        
    if not should_notify:
        return False
    
    try:
        recipients = get_notification_recipients(setting, work_order)
        if not recipients:
            return False
        
        subject = f"Hours {notification_type} - Work Order {work_order.rmj_job_number}"
        
        body = f"""
        A work order has reached {percentage:.1f}% of its estimated hours:
        
        RMJ Job Number: {work_order.rmj_job_number}
        Customer Work Order Number: {work_order.customer_work_order_number}
        Description: {work_order.description}
        
        Hours Logged: {hours_logged:.1f}
        Estimated Hours: {estimated_hours:.1f}
        Percentage: {percentage:.1f}%
        
        You can view the work order at: {url_for('work_order_detail', work_order_id=work_order.id, _external=True)}
        """
        
        msg = Message(subject=subject, recipients=recipients, body=body, sender=app.config['MAIL_DEFAULT_SENDER'])
        mail.send(msg)
        
        log_change(None, f"Sent Hours {notification_type} Notification", "Email", None, 
                  f"Sent hours threshold notification for Work Order #{work_order.id}")
        return True
    except Exception as e:
        print(f"Error sending hours threshold notification: {e}")
        return False

def send_scheduled_date_reminder(work_order):
    """Send reminder for upcoming scheduled date"""
    setting = get_notification_setting('scheduled_date')
    if not setting:
        return False
    
    options = setting.options
    days_before = options.get('days_before', 3)
    
    # Check if the scheduled date is coming up
    if not work_order.scheduled_date:
        return False
        
    days_until = (work_order.scheduled_date - datetime.now().date()).days
    
    if days_until != days_before:  # Only send exactly when we hit the threshold
        return False
    
    try:
        recipients = get_notification_recipients(setting, work_order)
        if not recipients:
            return False
        
        subject = f"Upcoming Work Order - {work_order.rmj_job_number}"
        
        body = f"""
        A work order is scheduled in {days_before} days:
        
        RMJ Job Number: {work_order.rmj_job_number}
        Customer Work Order Number: {work_order.customer_work_order_number}
        Description: {work_order.description}
        
        Scheduled Date: {work_order.scheduled_date.strftime('%Y-%m-%d')}
        
        You can view the work order at: {url_for('work_order_detail', work_order_id=work_order.id, _external=True)}
        """
        
        msg = Message(subject=subject, recipients=recipients, body=body, sender=app.config['MAIL_DEFAULT_SENDER'])
        mail.send(msg)
        
        log_change(None, "Sent Scheduled Date Reminder", "Email", None, 
                  f"Sent scheduled date reminder for Work Order #{work_order.id}")
        return True
    except Exception as e:
        print(f"Error sending scheduled date reminder: {e}")
        return False

def send_new_work_order_notification(work_order):
    """Send notification for new work order"""
    setting = get_notification_setting('new_work_order')
    if not setting:
        return False
    
    options = setting.options
    
    # Check if this priority level should trigger a notification
    should_notify = False
    if work_order.priority == 'High' and options.get('high_priority'):
        should_notify = True
    elif work_order.priority == 'Medium' and options.get('medium_priority'):
        should_notify = True
    elif work_order.priority == 'Low' and options.get('low_priority'):
        should_notify = True
        
    if not should_notify:
        return False
    
    try:
        recipients = get_notification_recipients(setting)
        if not recipients:
            return False
        
        subject = f"New Work Order Created - {work_order.rmj_job_number}"
        
        body = f"""
        A new work order has been created:
        
        RMJ Job Number: {work_order.rmj_job_number}
        Customer Work Order Number: {work_order.customer_work_order_number}
        Description: {work_order.description}
        
        Priority: {work_order.priority}
        Owner: {work_order.owner}
        Estimated Hours: {work_order.estimated_hours}
        
        You can view the work order at: {url_for('work_order_detail', work_order_id=work_order.id, _external=True)}
        """
        
        msg = Message(subject=subject, recipients=recipients, body=body, sender=app.config['MAIL_DEFAULT_SENDER'])
        mail.send(msg)
        
        log_change(None, "Sent New Work Order Notification", "Email", None, 
                  f"Sent notification for new Work Order #{work_order.id}")
        return True
    except Exception as e:
        print(f"Error sending new work order notification: {e}")
        return False

# Add a function to check scheduled date reminders (to be run daily)
def check_scheduled_date_reminders():
    """Check for work orders with upcoming scheduled dates and send reminders"""
    setting = get_notification_setting('scheduled_date')
    if not setting:
        return
    
    options = setting.options
    days_before = options.get('days_before', 3)
    
    # Calculate the date to check for
    target_date = datetime.now().date() + timedelta(days=days_before)
    
    # Find work orders scheduled for the target date
    work_orders = WorkOrder.query.filter_by(scheduled_date=target_date).all()
    
    for work_order in work_orders:
        send_scheduled_date_reminder(work_order)

@app.route('/admin/send_test_email', methods=['POST'])
@login_required
@admin_required
def send_test_email():
    """Send a test email to verify notification settings"""
    try:
        recipient = request.form.get('recipient')
        subject = request.form.get('subject', 'RMJ Dashboard Test Email')
        
        if not recipient:
            return jsonify({'success': False, 'message': 'No recipient provided'}), 400
            
        body = f"""
        This is a test email from the RMJ Dashboard notification system.
        
        If you received this email, your notification settings are working correctly.
        
        Time sent: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """
        
        msg = Message(subject=subject, recipients=[recipient], body=body, sender=app.config['MAIL_DEFAULT_SENDER'])
        mail.send(msg)
        
        # Log the test email
        log_change(
            session.get('user_id'),
            "Sent Test Email",
            "Email",
            None,
            f"Sent test email to {recipient}"
        )
        
        return jsonify({'success': True, 'message': f'Test email sent to {recipient}'})
    except Exception as e:
        print(f"Error sending test email: {e}")
        return jsonify({'success': False, 'message': f'Error sending email: {str(e)}'}), 500

@app.route('/admin/verify_email_configuration')
@login_required
@admin_required
def verify_email_configuration():
    """Verify that the email configuration is valid"""
    try:
        # Check if required email settings are present
        mail_server = app.config.get('MAIL_SERVER')
        mail_port = app.config.get('MAIL_PORT')
        mail_username = app.config.get('MAIL_USERNAME')
        mail_password = app.config.get('MAIL_PASSWORD')
        
        if not all([mail_server, mail_port, mail_username, mail_password]):
            return jsonify({
                'success': False,
                'message': 'Missing email configuration settings',
                'settings': {
                    'MAIL_SERVER': bool(mail_server),
                    'MAIL_PORT': bool(mail_port),
                    'MAIL_USERNAME': bool(mail_username),
                    'MAIL_PASSWORD': bool(mail_password)
                }
            })
        
        # Try to connect to the mail server
        import smtplib
        server = None
        if app.config.get('MAIL_USE_TLS'):
            server = smtplib.SMTP(mail_server, mail_port)
            server.starttls()
        else:
            server = smtplib.SMTP_SSL(mail_server, mail_port)
        
        server.login(mail_username, mail_password)
        server.quit()
        
        return jsonify({
            'success': True,
            'message': 'Email configuration is valid'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error verifying email configuration: {str(e)}'
        })



# =============================================================================
# AUTHENTICATION ROUTES
# =============================================================================
@app.route('/login', methods=['GET', 'POST'])
def login():
    """User login page"""
    error = None
    if request.method == 'POST':
         username = request.form.get('username')
         password = request.form.get('password')
         user = User.query.filter_by(username=username).first()
         if user and user.check_password(password):
              session['user_id'] = user.id
              session['user_role'] = user.role  # Store role in session
              return redirect(url_for('index'))
         else:
              error = "Invalid username or password"
    return render_template('login.html', error=error)


@app.route('/logout')
def logout():
    """Log out user by removing session data"""
    session.pop('user_id', None)
    return redirect(url_for('login'))


@app.route('/reset_password', methods=['GET', 'POST'])
def reset_password():
    """Allow users to reset their password"""
    error = None
    if request.method == 'POST':
        username = request.form.get('username')
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        # Look up the user by username.
        user = User.query.filter_by(username=username).first()
        if not user:
            error = "Invalid username."
        elif not user.check_password(current_password):
            error = "Current password is incorrect."
        elif new_password != confirm_password:
            error = "New password and confirmation do not match."
        else:
            user.set_password(new_password)
            db.session.commit()
            return redirect(url_for('login'))
    return render_template('reset_password.html', error=error)


# =============================================================================
# WORK ORDER ROUTES
# =============================================================================
@app.route('/')
@login_required
def index():
    """Main page displaying open work orders"""
    sort_by = request.args.get('sort_by', 'id')
    order = request.args.get('order', 'asc')
    work_orders = get_sorted_work_orders("Open", sort_by, order)
    return render_template('index.html', work_orders=work_orders, sort_by=sort_by, order=order)


@app.route('/workorders/completed')
@login_required
def completed_work_orders():
    """Page displaying completed work orders"""
    sort_by = request.args.get('sort_by', 'id')
    order = request.args.get('order', 'asc')
    work_orders = get_sorted_work_orders("Complete", sort_by, order)
    return render_template('completed_work_orders.html', work_orders=work_orders, sort_by=sort_by, order=order)


@app.route('/workorders/closed')
@login_required
def closed_work_orders():
    """Page displaying closed work orders"""
    sort_by = request.args.get('sort_by', 'id')
    order = request.args.get('order', 'asc')
    work_orders = get_sorted_work_orders("Closed", sort_by, order)
    return render_template('closed_work_orders.html', work_orders=work_orders, sort_by=sort_by, order=order)


@app.route('/workorder/new', methods=['GET', 'POST'])
@login_required
def new_work_order():
    """Create a new work order"""
    if request.method == 'POST':
        customer_work_order_number = request.form.get('customer_work_order_number')
        rmj_job_number = request.form.get('rmj_job_number')
        
        # Check for duplicate RMJ Job Number
        existing_work_order = WorkOrder.query.filter_by(rmj_job_number=rmj_job_number).first()
        if existing_work_order:
            error = "A work order with that RMJ Job Number already exists."
            return render_template('new_work_order.html', error=error)
        
        description = request.form.get('description')
        status = request.form.get('status')
        owner = request.form.get('owner')
        estimated_hours = float(request.form.get('estimated_hours') or 0)
        priority = request.form.get('priority')
        location = request.form.get('location')
        scheduled_date = parse_date(request.form.get('scheduled_date'))
        classification = request.form.get('classification', 'Billable')
        approved_for_work = False
        current_user = User.query.get(session.get('user_id'))
        if current_user and (current_user.role.lower() == 'admin' or current_user.username.lower() == 'admin'):
            approved_for_work = bool(request.form.get('approved_for_work'))
        
        new_order = WorkOrder(
            customer_work_order_number=customer_work_order_number,
            rmj_job_number=rmj_job_number,
            description=description,
            status=status,
            owner=owner,
            estimated_hours=estimated_hours,
            priority=priority,
            location=location,
            scheduled_date=scheduled_date,
            classification=classification,
            approved_for_work=approved_for_work
        )
        db.session.add(new_order)
        db.session.commit()
        
        # Log the creation
        log_change(session.get('user_id'), "Created WorkOrder", "WorkOrder", new_order.id,
                   f"Created work order with RMJ Job Number: {rmj_job_number}")
        db.session.commit()
        
        # Send new work order notification
        send_new_work_order_notification(new_order)
        
        return redirect(url_for('index'))
    return render_template('new_work_order.html')


@app.route('/workorder/<int:work_order_id>')
@login_required
def work_order_detail(work_order_id):
    """View details of a specific work order"""
    work_order = WorkOrder.query.get_or_404(work_order_id)
    # Find any associated project
    project = Project.query.filter_by(work_order_id=work_order.id).first()
    
    default_engineer = ""
    if session.get('user_id'):
        current_user = User.query.get(session.get('user_id'))
        if current_user:
            default_engineer = get_engineer_name(current_user.username)
    
    # Get all users for the dropdown, ordered by full_name
    users = User.query.order_by(User.full_name.nulls_last(), User.username).all()
    
    return render_template('work_order_detail.html', 
                         work_order=work_order, 
                         default_engineer=default_engineer, 
                         associated_project=project,
                         users=users)


@app.route('/workorder/<int:work_order_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_work_order(work_order_id):
    """Edit an existing work order"""
    work_order = WorkOrder.query.get_or_404(work_order_id)
    if request.method == 'POST':
        old_status = work_order.status  # Store old status for notification
        
        work_order.customer_work_order_number = request.form.get('customer_work_order_number')
        work_order.rmj_job_number = request.form.get('rmj_job_number')
        work_order.description = request.form.get('description')
        work_order.status = request.form.get('status')
        work_order.owner = request.form.get('owner')
        work_order.estimated_hours = float(request.form.get('estimated_hours', work_order.estimated_hours))
        work_order.priority = request.form.get('priority')
        work_order.location = request.form.get('location')
        work_order.scheduled_date = parse_date(request.form.get('scheduled_date'))
        work_order.classification = request.form.get('classification', "Billable")
        work_order.requested_by = request.form.get('requested_by')
        current_user = User.query.get(session.get('user_id'))
        if current_user and (current_user.role.lower() == 'admin' or current_user.username.lower() == 'admin'):
            work_order.approved_for_work = bool(request.form.get('approved_for_work'))
        
        db.session.commit()
        
        # Log the edit
        log_change(session.get('user_id'), "Edited WorkOrder", "WorkOrder", work_order.id,
                   f"Edited work order with RMJ Job Number: {work_order.rmj_job_number}")
        db.session.commit()
        
        # Send status change notification if status changed
        if old_status != work_order.status:
            send_status_change_notification(work_order, old_status, work_order.status)
        
        return redirect(url_for('work_order_detail', work_order_id=work_order.id))
    return render_template('edit_work_order.html', work_order=work_order)


@app.route('/workorder/<int:work_order_id>/delete', methods=['POST'])
@login_required
def delete_work_order(work_order_id):
    """Delete a work order"""
    password = request.form.get('password')
    if password != app.config.get('DELETE_PASSWORD'):
        return "Incorrect password", 403
    
    work_order = WorkOrder.query.get_or_404(work_order_id)
    rmj_job_number = work_order.rmj_job_number
    
    db.session.delete(work_order)
    db.session.commit()
    
    # Log deletion
    log_change(session.get('user_id'), "Deleted WorkOrder", "WorkOrder", work_order_id,
              f"Deleted work order with RMJ Job Number: {rmj_job_number}")
    db.session.commit()
    
    return redirect(url_for('index'))


@app.route('/workorder/<int:work_order_id>/download_report_template')
@login_required
def download_report_template(work_order_id):
    """Download a report template for a work order"""
    work_order = WorkOrder.query.get_or_404(work_order_id)
    return send_from_directory(
        'static', 
        'report_template.docx', 
        as_attachment=True, 
        download_name=f"WorkOrder_{work_order_id}_ReportTemplate.docx"
    )


@app.route('/search')
@login_required
def search():
    """Search for work orders by various criteria"""
    query = request.args.get('query', '')
    status = request.args.get('status', 'open')  # Default to 'open' if not specified
    
    # Determine the source page for the back button
    source_page = 'index'
    if status == 'closed':
        source_page = 'closed'
    elif status == 'completed':
        source_page = 'completed'
    elif status == 'all':
        source_page = 'all'
    
    if query:
        # Search by RMJ Job Number, Customer Work Order Number, or keywords in the description.
        search_filter = (
            WorkOrder.rmj_job_number.ilike(f'%{query}%') |
            WorkOrder.customer_work_order_number.ilike(f'%{query}%') |
            WorkOrder.description.ilike(f'%{query}%') |
            WorkOrder.owner.ilike(f'%{query}%') |
            WorkOrder.location.ilike(f'%{query}%')
        )
        
        # Apply status filter unless searching all
        if status == 'all':
            results = WorkOrder.query.filter(search_filter).all()
        else:
            results = WorkOrder.query.filter(search_filter & (WorkOrder.status == status)).all()
    else:
        results = []
    
    return render_template('search.html', query=query, results=results, source_page=source_page)


@app.route('/document/<int:document_id>/toggle_approval', methods=['POST'])
@login_required
def toggle_document_approval(document_id):
    """Toggle the approval status of a document"""
    document = WorkOrderDocument.query.get_or_404(document_id)
    
    # Get the updated approval status from the request
    data = request.get_json()
    is_approved = data.get('is_approved', False)
    
    # Update the document's approval status
    document.is_approved = is_approved
    
    # Log the change
    action = "Approved Document" if is_approved else "Unapproved Document"
    log_change(
        session.get('user_id'),
        action,
        "Document",
        document_id,
        f"{'Approved' if is_approved else 'Unapproved'} document {document.original_filename} for Work Order #{document.work_order_id}"
    )
    
    # Commit changes to the database
    db.session.commit()
    
    return jsonify({'success': True})

@app.route('/workorder/<int:work_order_id>/download_document/<int:document_id>')
@login_required
def download_document(work_order_id, document_id):
    # Fetch the WorkOrderDocument record (404 if not found)
    document = WorkOrderDocument.query.get_or_404(document_id)
    # Serve it from your UPLOAD_FOLDER with the original filename
    return send_from_directory(
        app.config['UPLOAD_FOLDER'],
        document.filename,
        as_attachment=True,
        download_name=document.original_filename
    )

@app.route('/workorder/<int:work_order_id>/document/<int:document_id>/delete', methods=['POST'])
@login_required
def delete_work_order_document(work_order_id, document_id):
    # Look up the document (404 if not found)
    document = WorkOrderDocument.query.get_or_404(document_id)
    # Ensure it belongs to this work order
    if document.work_order_id != work_order_id:
        return "Invalid document for this work order", 400

    # Remove the file from disk
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], document.filename)
    if os.path.exists(file_path):
        os.remove(file_path)

    # Delete the DB record
    db.session.delete(document)
    db.session.commit()

    flash(f"Deleted document “{document.original_filename}”", "success")
    return redirect(url_for('work_order_detail', work_order_id=work_order_id))

# =============================================================================
# TIME ENTRY ROUTES
# =============================================================================
@app.route('/workorder/<int:work_order_id>/add_time_inline', methods=['POST'])
@login_required
def add_time_inline(work_order_id):
    """Add a time entry directly from the work order detail page"""
    work_order = WorkOrder.query.get_or_404(work_order_id)
    # Prevent adding time if the work order is closed or complete.
    if work_order.status in ["Closed", "Complete"]:
        return "Cannot add time entries to a closed or complete work order.", 403

    # Get the engineer from the dropdown (user_id) or fallback to text input
    selected_user_id = request.form.get('engineer_user')
    if selected_user_id:
        selected_user = User.query.get(int(selected_user_id))
        engineer = get_engineer_name(selected_user.username) if selected_user else ""
    else:
        engineer = request.form.get('engineer')
        
    # If the engineer field is still empty, map the logged-in user's username to a full name.
    if not engineer or engineer.strip() == "":
        current_user = User.query.get(session.get('user_id'))
        if current_user:
            engineer = get_engineer_name(current_user.username)
        else:
            engineer = ""
    
    work_date_str = request.form.get('work_date')
    time_in_str = request.form.get('time_in')
    time_out_str = request.form.get('time_out')
    description = request.form.get('description')

    try:
        work_date = parse_date(work_date_str)
        time_in = parse_time(time_in_str)
        time_out = parse_time(time_out_str)
        if not all([work_date, time_in, time_out]):
            return "Invalid date or time format", 400
    except Exception:
        return "Invalid date or time format", 400

    # Check for time overlap
    overlap_check = check_time_overlap(work_order_id, engineer, work_date, time_in, time_out)
    if overlap_check['overlap']:
        flash(overlap_check['message'], 'danger')
        return redirect(url_for('work_order_detail', work_order_id=work_order_id))

    hours_worked = calculate_hours(work_date, time_in, time_out)

    # Handle lunch deduction
    had_lunch = request.form.get('had_lunch') == 'on'
    lunch_start = None
    lunch_end = None
    lunch_deduction = 0.0

    if had_lunch:
        lunch_start_str = request.form.get('lunch_start')
        lunch_end_str = request.form.get('lunch_end')
        
        if lunch_start_str and lunch_end_str:
            lunch_start = parse_time(lunch_start_str)
            lunch_end = parse_time(lunch_end_str)
            
            # Validate lunch timing (must be within 6 hours of start)
            lunch_validation = validate_lunch_timing(time_in, lunch_end)
            if not lunch_validation['valid']:
                flash(lunch_validation['message'], 'danger')
                return redirect(url_for('work_order_detail', work_order_id=work_order_id))
            
            # Calculate overlap between work time and lunch time
            lunch_deduction = calculate_lunch_overlap(work_date, time_in, time_out, lunch_start, lunch_end)

    # Also check if other entries on the same day have lunch that overlaps with this work time
    cross_entry_lunch = calculate_cross_entry_lunch(work_order_id, engineer, work_date, time_in, time_out)
    lunch_deduction += cross_entry_lunch

    if lunch_deduction > 0:
        hours_worked = max(0, hours_worked - lunch_deduction)

    new_entry = TimeEntry(
        work_order_id=work_order_id,
        engineer=engineer,
        work_date=work_date,
        time_in=time_in,
        time_out=time_out,
        hours_worked=hours_worked,
        lunch_deduction=lunch_deduction,
        lunch_start=lunch_start,
        lunch_end=lunch_end,
        description=description
    )
    db.session.add(new_entry)
    db.session.commit()  # Commit to generate new_entry.id

    # Log the creation of the time entry.
    log_change(
        session.get('user_id'),
        "Created TimeEntry",
        "TimeEntry",
        new_entry.id,
        f"Added time entry for engineer {engineer} with {hours_worked} hours on work order {work_order.rmj_job_number}"
    )
    db.session.commit()
    
    # Check hours threshold after adding time
    if work_order.estimated_hours > 0:
        hours_logged = work_order.hours_logged
        percentage = (hours_logged / work_order.estimated_hours) * 100
        
        # Check thresholds setting
        setting = get_notification_setting('hours_threshold')
        if setting:
            warning_threshold = setting.options.get('warning_threshold', 80)
            
            # Check if we've just crossed a threshold
            if (percentage >= warning_threshold and (percentage - (hours_worked / work_order.estimated_hours * 100)) < warning_threshold) or \
               (percentage >= 100 and (percentage - (hours_worked / work_order.estimated_hours * 100)) < 100):
                send_hours_threshold_notification(
                    work_order, 
                    hours_logged, 
                    work_order.estimated_hours, 
                    percentage
                )

    return redirect(url_for('work_order_detail', work_order_id=work_order.id))


@app.route('/time_entry/<int:time_entry_id>/delete', methods=['POST'])
@login_required
def delete_time_entry(time_entry_id):
    """Delete a time entry"""
    entry = TimeEntry.query.get_or_404(time_entry_id)
    
    # Check if entry is locked due to JL/JT checkboxes
    if entry.entered_on_jl or entry.entered_on_jt:
        flash("Cannot delete time entry: This entry has been entered into the accounting system (JL/JT checked).", "danger")
        return redirect(url_for('work_order_detail', work_order_id=entry.work_order_id))
    
    work_order_id = entry.work_order_id
    
    # Log the deletion
    log_change(
        session.get('user_id'),
        "Deleted TimeEntry",
        "TimeEntry",
        time_entry_id,
        f"Deleted time entry for engineer {entry.engineer} with {entry.hours_worked} hours"
    )
    
    db.session.delete(entry)
    db.session.commit()
    
    flash("Time entry deleted successfully.", "success")
    return redirect(url_for('work_order_detail', work_order_id=work_order_id))


@app.route('/time_entry/<int:time_entry_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_time_entry(time_entry_id):
    """Edit an existing time entry"""
    entry = TimeEntry.query.get_or_404(time_entry_id)
    
    # Check if entry is locked due to JL/JT checkboxes
    if entry.entered_on_jl or entry.entered_on_jt:
        flash("Cannot edit time entry: This entry has been entered into the accounting system (JL/JT checked).", "danger")
        return redirect(url_for('work_order_detail', work_order_id=entry.work_order_id))
    
    if request.method == 'POST':
        engineer = request.form.get('engineer')
        work_date_str = request.form.get('work_date')
        time_in_str = request.form.get('time_in')
        time_out_str = request.form.get('time_out')
        description = request.form.get('description')
        
        try:
            work_date = parse_date(work_date_str)
            time_in = parse_time(time_in_str)
            time_out = parse_time(time_out_str)
            if not all([work_date, time_in, time_out]):
                flash("Invalid date or time format", "danger")
                return render_template('edit_time_entry.html', entry=entry)
        except Exception as e:
            flash(f"Invalid date or time format: {e}", "danger")
            return render_template('edit_time_entry.html', entry=entry)
            
        entry.engineer = engineer
        entry.work_date = work_date
        entry.time_in = time_in
        entry.time_out = time_out
        entry.description = description
        entry.hours_worked = calculate_hours(work_date, time_in, time_out)
        
        # Log the edit
        log_change(
            session.get('user_id'),
            "Edited TimeEntry",
            "TimeEntry",
            entry.id,
            f"Edited time entry for engineer {entry.engineer}"
        )
        
        db.session.commit()
        flash("Time entry updated successfully.", "success")
        return redirect(url_for('work_order_detail', work_order_id=entry.work_order_id))
    
    return render_template('edit_time_entry.html', entry=entry)


@app.route('/time_entry/<int:time_entry_id>/reassign', methods=['GET', 'POST'])
@login_required
def reassign_time_entry(time_entry_id):
    """Reassign a time entry to a different work order"""
    entry = TimeEntry.query.get_or_404(time_entry_id)
    
    # Check if entry is locked due to JL/JT checkboxes
    if entry.entered_on_jl or entry.entered_on_jt:
        flash("Cannot reassign time entry: This entry has been entered into the accounting system (JL/JT checked).", "danger")
        return redirect(url_for('work_order_detail', work_order_id=entry.work_order_id))
    
    if request.method == 'POST':
        target_work_order_id = request.form.get('target_work_order_id')
        if not target_work_order_id:
            flash("Please select a target work order", "danger")
            work_orders = WorkOrder.query.all()
            return render_template('reassign_time_entry.html', entry=entry, work_orders=work_orders)
        
        old_work_order_id = entry.work_order_id
        entry.work_order_id = int(target_work_order_id)
        
        # Log the reassignment
        log_change(
            session.get('user_id'),
            "Reassigned TimeEntry",
            "TimeEntry",
            entry.id,
            f"Reassigned time entry from work order {old_work_order_id} to {target_work_order_id}"
        )
        
        db.session.commit()
        flash("Time entry reassigned successfully.", "success")
        return redirect(url_for('work_order_detail', work_order_id=entry.work_order_id))
    else:
        work_orders = WorkOrder.query.all()
        return render_template('reassign_time_entry.html', entry=entry, work_orders=work_orders)


@app.route('/time_entry/<int:entry_id>/update_checkboxes', methods=['POST'])
@login_required
@rate_limit(max_calls=10, time_window=10)
def update_time_entry_checkboxes(entry_id):
    """Update the checkbox status for a time entry"""
    try:
        entry = TimeEntry.query.get_or_404(entry_id)
        data = request.get_json()  # Expecting JSON data
        
        # Check if data was received
        if not data:
            return jsonify({'success': False, 'message': 'No data received'}), 400
        
        # Update the checkboxes if data is provided
        if 'entered_on_jl' in data:
            entry.entered_on_jl = bool(data['entered_on_jl'])
        if 'entered_on_jt' in data:
            entry.entered_on_jt = bool(data['entered_on_jt'])
        
        # Commit the changes
        db.session.commit()
        
        # Return success response
        return jsonify({'success': True})
        
    except Exception as e:
        # Log the error for debugging
        print(f"Error in update_time_entry_checkboxes: {str(e)}")
        db.session.rollback()  # Rollback any pending changes
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/workorder/<int:work_order_id>/export_time_entries')
@login_required
def export_time_entries_for_work_order(work_order_id):
    """Export time entries for a work order to Excel"""
    work_order = WorkOrder.query.get_or_404(work_order_id)
    time_entries = TimeEntry.query.filter_by(work_order_id=work_order.id).order_by(TimeEntry.work_date).all()
    
    if not time_entries:
        return "No time entries found for this work order.", 404

    data = []
    for entry in time_entries:
        data.append({
            "ID": entry.id,
            "Engineer": entry.engineer,
            "Work Date": entry.work_date.strftime('%Y-%m-%d'),
            "Time In": entry.time_in.strftime('%H:%M'),
            "Time Out": entry.time_out.strftime('%H:%M'),
            "Hours Worked": entry.hours_worked,
            "Description": entry.description,
            "Logged At": entry.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        })

    df = pd.DataFrame(data)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='TimeEntries')
    output.seek(0)

    filename = f"WorkOrder_{work_order.id}_TimeEntries.xlsx"
    return send_file(output, download_name=filename, as_attachment=True,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@app.route('/time_entry/<int:entry_id>/update', methods=['POST'])
@login_required
def update_time_entry_ajax(entry_id):
    """Update a time entry via AJAX request"""
    entry = TimeEntry.query.get_or_404(entry_id)
    
    # Check if entry is locked due to JL/JT checkboxes
    if entry.entered_on_jl or entry.entered_on_jt:
        return jsonify({
            'success': False,
            'error': 'Cannot update time entry: This entry has been entered into the accounting system (JL/JT checked).'
        }), 403
    
    data = request.get_json()
    
    try:
        entry.engineer = data.get('engineer')
        entry.work_date = parse_date(data.get('work_date'))
        entry.time_in = parse_time(data.get('time_in')) 
        entry.time_out = parse_time(data.get('time_out'))
        entry.description = data.get('description')
        
        # Recalculate hours worked
        base_hours = calculate_hours(entry.work_date, entry.time_in, entry.time_out)

        # Recalculate lunch deductions
        lunch_deduction = 0.0
        if entry.lunch_start and entry.lunch_end:
            lunch_deduction = calculate_lunch_overlap(entry.work_date, entry.time_in, entry.time_out, entry.lunch_start, entry.lunch_end)

        # Check for cross-entry lunch overlaps
        cross_entry_lunch = calculate_cross_entry_lunch(entry.work_order_id, entry.engineer, entry.work_date, entry.time_in, entry.time_out, exclude_entry_id=entry.id)
        lunch_deduction += cross_entry_lunch

        entry.lunch_deduction = lunch_deduction
        entry.hours_worked = max(0, base_hours - lunch_deduction)

        # Log the update
        log_change(
            session.get('user_id'),
            "Updated TimeEntry via AJAX",
            "TimeEntry",
            entry.id,
            f"Updated time entry for engineer {entry.engineer}"
        )
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'hours_worked': entry.hours_worked
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

# Add this route to app.py in the TIME ENTRY ROUTES section

@app.route('/workorder/<int:work_order_id>/add_time_adjustment', methods=['POST'])
@login_required
@admin_required
def add_time_adjustment(work_order_id):
    """Add a time adjustment entry (admin only)"""
    work_order = WorkOrder.query.get_or_404(work_order_id)
    
    # Get the form fields from the adjustment form
    work_date_str = request.form.get('adjustment_work_date')
    hours_adjustment = request.form.get('hours_adjustment')
    description = request.form.get('adjustment_description')

    try:
        work_date = parse_date(work_date_str)
        hours_float = float(hours_adjustment)
        
        if not work_date:
            flash("Invalid date format", "danger")
            return redirect(url_for('work_order_detail', work_order_id=work_order_id))
            
        if hours_float == 0:
            flash("Hours adjustment cannot be zero", "warning")
            return redirect(url_for('work_order_detail', work_order_id=work_order_id))
            
    except (ValueError, TypeError):
        flash("Invalid hours format", "danger")
        return redirect(url_for('work_order_detail', work_order_id=work_order_id))

    # For time adjustments, we'll use dummy time values since they're required fields
    # but not meaningful for adjustments
    if hours_float > 0:
        # Positive adjustment: time_in = 09:00, time_out = 09:00 + hours
        time_in = time_class(9, 0)  # Use time_class instead of time
        hours_part = int(hours_float)
        minutes_part = int((hours_float % 1) * 60)
        time_out_dt = datetime.combine(work_date, time_in) + timedelta(hours=hours_part, minutes=minutes_part)
        time_out = time_out_dt.time()
    else:
        # Negative adjustment: time_in = 09:00, time_out = 09:00 (will show 0 hours but we'll override)
        time_in = time_class(9, 0)  # Use time_class instead of time
        time_out = time_class(9, 0)  # Use time_class instead of time

    new_entry = TimeEntry(
        work_order_id=work_order_id,
        engineer="timeadj",  # Hard-coded engineer name for adjustments
        work_date=work_date,
        time_in=time_in,
        time_out=time_out,
        hours_worked=hours_float,  # This can be negative
        description=description or "Time adjustment"
    )
    db.session.add(new_entry)
    db.session.commit()

    # Log the creation of the time adjustment
    log_change(
        session.get('user_id'),
        "Created Time Adjustment",
        "TimeEntry",
        new_entry.id,
        f"Added time adjustment of {hours_float} hours on work order {work_order.rmj_job_number}"
    )
    db.session.commit()
    
    # Flash appropriate message
    if hours_float > 0:
        flash(f"Added time adjustment of +{hours_float} hours", "success")
    else:
        flash(f"Added time adjustment of {hours_float} hours", "info")

    return redirect(url_for('work_order_detail', work_order_id=work_order.id))

# =============================================================================
# TIMESHEET ROUTES
# =============================================================================
@app.route('/timesheet/new', methods=['GET', 'POST'])
@login_required
def new_timesheet():
    """Create a new timesheet with multiple time entries"""
    default_engineer = ""
    current_user_id = None
    if session.get('user_id'):
        current_user = User.query.get(session.get('user_id'))
        if current_user:
            default_engineer = get_engineer_name(current_user.username)
            current_user_id = current_user.id
    
    if request.method == 'POST':
        entries_created = 0
        for i in range(1, 6):
            work_order_id = request.form.get(f'work_order_id_{i}')
            if work_order_id:
                wo = WorkOrder.query.get(int(work_order_id))
                if wo and wo.status in ["Closed", "Complete"]:
                    continue

                # Get the engineer from the dropdown (user_id) or fallback to text input
                selected_user_id = request.form.get(f'engineer_user_{i}')
                if selected_user_id:
                    selected_user = User.query.get(int(selected_user_id))
                    engineer = get_engineer_name(selected_user.username) if selected_user else default_engineer
                else:
                    engineer = request.form.get(f'engineer_{i}') or default_engineer
                
                work_date_str = request.form.get(f'work_date_{i}')
                time_in_str = request.form.get(f'time_in_{i}')
                time_out_str = request.form.get(f'time_out_{i}')
                description = request.form.get(f'description_{i}')
                
                try:
                    work_date = parse_date(work_date_str)
                    time_in = parse_time(time_in_str)
                    time_out = parse_time(time_out_str)
                    if not all([work_date, time_in, time_out]):
                        continue
                except Exception:
                    continue

                # Check for time overlap with existing entries
                overlap_check = check_time_overlap(int(work_order_id), engineer, work_date, time_in, time_out)
                if overlap_check['overlap']:
                    flash(f"Entry {i}: {overlap_check['message']}", 'danger')
                    work_orders = WorkOrder.query.all()
                    users = User.query.order_by(User.full_name.nulls_last(), User.username).all()
                    return render_template('timesheet_new.html', 
                                        work_orders=work_orders, 
                                        default_engineer=default_engineer,
                                        current_user_id=current_user_id,
                                        users=users)

                hours_worked = calculate_hours(work_date, time_in, time_out)

                # Handle lunch deduction
                had_lunch = request.form.get(f'had_lunch_{i}') == 'on'
                lunch_start = None
                lunch_end = None
                lunch_deduction = 0.0

                if had_lunch:
                    lunch_start_str = request.form.get(f'lunch_start_{i}')
                    lunch_end_str = request.form.get(f'lunch_end_{i}')
                    
                    if lunch_start_str and lunch_end_str:
                        lunch_start = parse_time(lunch_start_str)
                        lunch_end = parse_time(lunch_end_str)
                        
                        # Validate lunch timing (must be within 6 hours of start)
                        lunch_validation = validate_lunch_timing(time_in, lunch_end)
                        if not lunch_validation['valid']:
                            flash(f"Entry {i}: {lunch_validation['message']}", 'danger')
                            work_orders = WorkOrder.query.all()
                            users = User.query.order_by(User.full_name.nulls_last(), User.username).all()
                            return render_template('timesheet_new.html', 
                                                work_orders=work_orders, 
                                                default_engineer=default_engineer,
                                                current_user_id=current_user_id,
                                                users=users)
                        
                        # Calculate overlap between work time and lunch time
                        lunch_deduction = calculate_lunch_overlap(work_date, time_in, time_out, lunch_start, lunch_end)

                # Also check if other entries on the same day have lunch that overlaps with this work time
                cross_entry_lunch = calculate_cross_entry_lunch(int(work_order_id), engineer, work_date, time_in, time_out)
                lunch_deduction += cross_entry_lunch

                if lunch_deduction > 0:
                    hours_worked = max(0, hours_worked - lunch_deduction)

                new_entry = TimeEntry(
                    work_order_id=int(work_order_id),
                    engineer=engineer,
                    work_date=work_date,
                    time_in=time_in,
                    time_out=time_out,
                    hours_worked=hours_worked,
                    lunch_deduction=lunch_deduction,
                    lunch_start=lunch_start,
                    lunch_end=lunch_end,
                    description=description
                )
                db.session.add(new_entry)
                entries_created += 1
        db.session.commit()
        if entries_created > 0:
            return redirect(url_for('index'))
        else:
            return "No valid entries submitted", 400
    else:
        work_orders = WorkOrder.query.all()
        # Get all users for the dropdown, ordered by full_name
        users = User.query.order_by(User.full_name.nulls_last(), User.username).all()
        
        return render_template('timesheet_new.html', 
                             work_orders=work_orders, 
                             default_engineer=default_engineer,
                             current_user_id=current_user_id,
                             users=users)


@app.route('/timesheet/select', methods=['GET', 'POST'])
@login_required
def select_weekly_timesheet():
    """Select a weekly timesheet to view"""
    if request.method == 'POST':
        year = request.form.get('year')
        week = request.form.get('week')
        try:
            year = int(year)
            week = int(week)
        except ValueError:
            return "Invalid input", 400
        return redirect(url_for('view_weekly_timesheet', year=year, week=week))
    else:
        current_year = date.today().year
        try:
            year = int(request.args.get('year', current_year))
        except ValueError:
            year = current_year

        jan1 = date(year, 1, 1)
        offset = (jan1.weekday() + 1) % 7
        first_sunday = jan1 - timedelta(days=offset)

        week_options = []
        for n in range(1, 53):
            week_sunday = first_sunday + timedelta(days=(n - 1) * 7)
            week_saturday = week_sunday + timedelta(days=6)
            option_text = f"Week {n}: {week_sunday.strftime('%Y-%m-%d')} to {week_saturday.strftime('%Y-%m-%d')}"
            week_options.append((n, option_text))
        
        return render_template('select_timesheet.html', year=year, week_options=week_options)


@app.route('/timesheet/weeks/<int:year>')
@login_required
def get_week_options(year):
    """Get week options for a specific year"""
    jan1 = date(year, 1, 1)
    offset = (jan1.weekday() + 1) % 7
    first_sunday = jan1 - timedelta(days=offset)
    
    week_options = []
    for n in range(1, 53):
        week_sunday = first_sunday + timedelta(days=(n - 1) * 7)
        week_saturday = week_sunday + timedelta(days=6)
        option_text = f"Week {n}: {week_sunday.strftime('%Y-%m-%d')} to {week_saturday.strftime('%Y-%m-%d')}"
        week_options.append({'week': n, 'text': option_text})
    return jsonify(week_options)


@app.route('/timesheet/<int:year>/<int:week>')
@login_required
def view_weekly_timesheet(year, week):
    """View a weekly timesheet"""
    start_date, last_date = get_week_dates(year, week)
    if not start_date or not last_date:
        return "Invalid year/week combination", 400
    
    sort_by = request.args.get('sort_by', 'work_date')
    order = request.args.get('order', 'asc')
    
    valid_sort_columns = {
        'work_date': TimeEntry.work_date,
        'engineer': TimeEntry.engineer,
    }
    sort_column = valid_sort_columns.get(sort_by, TimeEntry.work_date)
    sort_order = sort_column.asc() if order == 'asc' else sort_column.desc()
    
    engineer_filter = request.args.get('engineer', None)
    query = TimeEntry.query.filter(TimeEntry.work_date >= start_date, TimeEntry.work_date <= last_date)
    if engineer_filter:
        query = query.filter(TimeEntry.engineer.ilike(f'%{engineer_filter}%'))
    time_entries = query.order_by(sort_order).all()
    total_hours = sum(entry.hours_worked for entry in time_entries)
    
    return render_template('weekly_timesheet.html',
                           year=year,
                           week=week,
                           start_date=start_date,
                           last_date=last_date,
                           time_entries=time_entries,
                           total_hours=total_hours,
                           sort_by=sort_by,
                           order=order)


@app.route('/timesheet/export/<int:year>/<int:week>')
@login_required
def export_timesheet(year, week):
    """Export a weekly timesheet to Excel"""
    start_date, last_date = get_week_dates(year, week)
    if not start_date or not last_date:
        return "Invalid year/week combination", 400
    
    query = TimeEntry.query.filter(
        TimeEntry.work_date >= start_date,
        TimeEntry.work_date <= last_date
    )
    
    engineer_filter = request.args.get('engineer', None)
    if engineer_filter:
        query = query.filter(TimeEntry.engineer.ilike(f'%{engineer_filter}%'))
    
    time_entries = query.order_by(TimeEntry.work_date).all()

    if not time_entries:
        return "No time entries found for this query.", 404

    data = []
    for entry in time_entries:
        data.append({
            'ID': entry.id,
            'Engineer': entry.engineer,
            'Work Order': f"{entry.work_order.rmj_job_number} - {entry.work_order.customer_work_order_number}",
            'Date': entry.work_date.strftime('%Y-%m-%d'),
            'Time In': entry.time_in.strftime('%H:%M'),
            'Time Out': entry.time_out.strftime('%H:%M'),
            'Hours Worked': entry.hours_worked,
            'Description': entry.description,
        })
    
    df = pd.DataFrame(data)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Timesheet')
    output.seek(0)
    
    filename = f"Timesheet_{year}_week{week}.xlsx"
    return send_file(
        output,
        download_name=filename,
        as_attachment=True,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

@app.route('/timesheet/ajax/entries_by_date')
@login_required
def get_entries_by_date():
    """API endpoint to get time entries for a specific date"""
    try:
        # Get the date parameter
        date_str = request.args.get('date')
        year = int(request.args.get('year'))
        week = int(request.args.get('week'))
        
        # Parse the date
        entry_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        
        # Get all time entries for this date within the current filter context
        query = TimeEntry.query.filter(TimeEntry.work_date == entry_date)
        
        # Apply any filters that were applied to the main view
        engineer_filter = request.args.get('engineer', None)
        if engineer_filter:
            query = query.filter(TimeEntry.engineer.ilike(f'%{engineer_filter}%'))
            
        # Get the entries
        entries = query.all()
        
        # Format the entries for JSON response
        result = []
        for entry in entries:
            result.append({
                'id': entry.id,
                'engineer': entry.engineer,
                'time_in': entry.time_in.strftime('%H:%M'),
                'time_out': entry.time_out.strftime('%H:%M'),
                'hours_worked': float(entry.hours_worked),
                'work_order': entry.work_order.rmj_job_number,
                'description': entry.description,
                'classification': entry.work_order.classification
            })
        
        return jsonify({'success': True, 'entries': result})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# =============================================================================
# DOCUMENT UPLOAD ROUTES
# =============================================================================
@app.route('/workorder/<int:work_order_id>/upload_document', methods=['GET', 'POST'])
@login_required
def upload_document(work_order_id):
    work_order = WorkOrder.query.get_or_404(work_order_id)
    # Get associated project if it exists
    associated_project = Project.query.filter_by(work_order_id=work_order_id).first()
    
    if request.method == 'POST':
        if 'document' not in request.files:
            return "No file part", 400
        file = request.files['document']
        if file.filename == '':
            return "No file selected", 400
        filename = secure_filename(file.filename)
        
        # Create upload folder if it doesn't exist
        upload_folder = app.config['UPLOAD_FOLDER']
        if not os.path.exists(upload_folder):
            os.makedirs(upload_folder)
        
        # Save file locally
        file_path = os.path.join(upload_folder, filename)
        file.save(file_path)
        
        # Get document type from form
        document_type = request.form.get('document_type', 'regular')
        
        # Create document record with local file path
        document = WorkOrderDocument(
            work_order_id=work_order_id,
            project_id=associated_project.id if associated_project else None,
            filename=filename,
            original_filename=file.filename,
            upload_time=datetime.utcnow(),
            document_type=document_type
        )
        
        db.session.add(document)
        db.session.commit()
        
        # Check if notifications are enabled and determine document type
        is_report = (document_type == 'report') or is_report_file(file.filename)
        
        # Send appropriate notifications
        notification_sent = False
        
        if is_report:
            # Send report upload notification
            if send_report_notification(work_order, document):
                notification_sent = True
                flash("Report uploaded and notification sent.", "success")
            
            # Send report approval notification if enabled
            approval_setting = get_notification_setting('report_approval')
            if approval_setting:
                if send_report_approval_notification(work_order, document):
                    flash("Report approval notification sent.", "success")
                else:
                    flash("Report approval notification failed to send.", "warning")
        
        if not notification_sent:
            flash("Document uploaded successfully.", "success")
            
        return redirect(url_for('work_order_detail', work_order_id=work_order_id))
        
    return render_template('upload_document.html', work_order=work_order)


# =============================================================================
# IMPORT/EXPORT ROUTES
# =============================================================================
@app.route('/import', methods=['GET', 'POST'])
@login_required
def import_excel():
    """Import work orders from Excel"""
    if request.method == 'POST':
        if 'file' not in request.files:
            return "No file part", 400
        file = request.files['file']
        if file.filename == '':
            return "No selected file", 400
        try:
            df = pd.read_excel(file)
            for index, row in df.iterrows():
                scheduled_date = None
                if 'scheduled_date' in row and not pd.isna(row['scheduled_date']):
                    try:
                        scheduled_date = pd.to_datetime(row['scheduled_date']).date()
                    except Exception:
                        scheduled_date = None
                work_order = WorkOrder(
                    customer_work_order_number=row.get('customer_work_order_number', ''),
                    rmj_job_number=row.get('rmj_job_number', ''),
                    description=row.get('description', ''),
                    status=row.get('status', ''),
                    owner=row.get('owner', ''),
                    estimated_hours=float(row.get('estimated_hours', 0)),
                    priority=row.get('priority', 'Medium'),
                    location=row.get('location', ''),
                    scheduled_date=scheduled_date
                )
                db.session.add(work_order)
            db.session.commit()
            return redirect(url_for('index'))
        except Exception as e:
            return f"Error processing file: {e}", 400
    return render_template('import.html')


@app.route('/export')
@login_required
def export_excel():
    """Export all work orders to Excel"""
    work_orders = WorkOrder.query.all()
    data = []
    for wo in work_orders:
        data.append({
            "ID": wo.id,
            "Customer Work Order Number": wo.customer_work_order_number,
            "RMJ Job Number": wo.rmj_job_number,
            "Description": wo.description,
            "Status": wo.status,
            "Owner": wo.owner,
            "Estimated Hours": wo.estimated_hours,
            "Hours Logged": wo.hours_logged,
            "Hours Remaining": wo.hours_remaining,
            "Priority": wo.priority,
            "Location": wo.location,
            "Scheduled Date": wo.scheduled_date.strftime('%Y-%m-%d') if wo.scheduled_date else ''
        })
    df = pd.DataFrame(data)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='WorkOrders')
    output.seek(0)
    return send_file(output, download_name="workorders.xlsx", as_attachment=True, 
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


# =============================================================================
# PROJECT ROUTES
# =============================================================================
@app.route('/projects')
@login_required
def projects():
    """View all projects"""
    projects = Project.query.all()
    # Filter for only projects related to Contract/Project work orders
    contract_projects = []
    for project in projects:
        if project.work_order and project.work_order.classification == 'Contract/Project':
            contract_projects.append(project)
    return render_template('project_dashboard.html', projects=contract_projects)


@app.route('/projects/new', methods=['GET', 'POST'])
@login_required
def new_project():
    """Create a new project"""
    if request.method == 'POST':
        work_order_id = request.form.get('work_order_id')
        name = request.form.get('name')
        description = request.form.get('description')
        start_date = parse_date(request.form.get('start_date'))
        end_date = parse_date(request.form.get('end_date'))
        
        # Validate the work order exists and is a Contract/Project type
        work_order = WorkOrder.query.get_or_404(int(work_order_id))
        if work_order.classification != 'Contract/Project':
            return "Only Contract/Project work orders can have associated projects", 400
        
        # Check if this work order already has a project
        existing_project = Project.query.filter_by(work_order_id=work_order_id).first()
        if existing_project:
            return "This work order already has an associated project", 400
        
        new_project = Project(
            work_order_id=work_order_id,
            name=name,
            description=description,
            start_date=start_date,
            end_date=end_date,
            status='Planning'
        )
        db.session.add(new_project)
        db.session.commit()
        
        # Log the creation
        log_change(session.get('user_id'), "Created Project", "Project", new_project.id,
                   f"Created project '{name}' for Work Order #{work_order_id}")
        db.session.commit()
        
        return redirect(url_for('project_detail', project_id=new_project.id))
    
    # Get all Contract/Project work orders that don't already have projects
    work_orders = WorkOrder.query.filter_by(classification='Contract/Project').all()
    eligible_work_orders = []
    for wo in work_orders:
        if not Project.query.filter_by(work_order_id=wo.id).first():
            eligible_work_orders.append(wo)
            
    return render_template('new_project.html', work_orders=eligible_work_orders)


@app.route('/projects/<int:project_id>')
@login_required
def project_detail(project_id):
    """View project details"""
    project = Project.query.get_or_404(project_id)
    
    # Get the default engineer name for the form
    default_engineer = ""
    if session.get('user_id'):
        current_user = User.query.get(session.get('user_id'))
        if current_user:
            default_engineer = get_engineer_name(current_user.username)
    
    # Today's date for the form
    today_date = datetime.now().strftime('%Y-%m-%d')
    
    # Get all users for the assigned_to dropdown
    users = User.query.order_by(User.full_name).all()
    
    return render_template(
        'project_detail.html', 
        project=project, 
        default_engineer=default_engineer, 
        today_date=today_date,
        users=users
    )


@app.route('/projects/<int:project_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_project(project_id):
    """Edit a project"""
    project = Project.query.get_or_404(project_id)
    if request.method == 'POST':
        project.name = request.form.get('name')
        project.description = request.form.get('description')
        project.start_date = parse_date(request.form.get('start_date'))
        project.end_date = parse_date(request.form.get('end_date'))
        project.status = request.form.get('status')
        
        db.session.commit()
        
        # Log the edit
        log_change(session.get('user_id'), "Edited Project", "Project", project.id,
                   f"Edited project '{project.name}'")
        db.session.commit()
        
        return redirect(url_for('project_detail', project_id=project.id))
    return render_template('edit_project.html', project=project)


@app.route('/projects/<int:project_id>/delete', methods=['POST'])
@login_required
def delete_project(project_id):
    """Delete a project"""
    project = Project.query.get_or_404(project_id)
    project_name = project.name
    
    # Unlink any time entries from tasks in this project
    for task in project.tasks:
        for entry in task.time_entries:
            entry.task_id = None
    
    # Delete the project (will cascade delete tasks due to relationship)
    db.session.delete(project)
    
    # Log the deletion
    log_change(
        session.get('user_id'),
        "Deleted Project",
        "Project",
        project_id,
        f"Deleted project '{project_name}' and all associated tasks"
    )
    
    db.session.commit()
    
    return redirect(url_for('projects'))


@app.route('/projects/<int:project_id>/upload_document', methods=['GET', 'POST'])
@login_required
def upload_project_document(project_id):
    """Upload a document for a project"""
    project = Project.query.get_or_404(project_id)
    work_order = WorkOrder.query.get_or_404(project.work_order_id)
    
    if request.method == 'POST':
        if 'document' not in request.files:
            return "No file part", 400
        file = request.files['document']
        if file.filename == '':
            return "No file selected", 400
        filename = secure_filename(file.filename)
        
        # Create upload folder if it doesn't exist
        upload_folder = app.config['UPLOAD_FOLDER']
        if not os.path.exists(upload_folder):
            os.makedirs(upload_folder)
            
        file_path = os.path.join(upload_folder, filename)
        file.save(file_path)
        
        # Get document type from form
        document_type = request.form.get('document_type', 'regular')
        
        # Create document linked to both work order and project
        document = WorkOrderDocument(
            work_order_id=project.work_order_id,
            project_id=project_id,
            filename=filename,
            original_filename=file.filename,
            upload_time=datetime.utcnow(),
            document_type=document_type
        )
        db.session.add(document)
        db.session.commit()
        
        return redirect(url_for('project_detail', project_id=project_id))
        
    # Change this line to use the existing template and pass both project and work_order
    return render_template('upload_document.html', work_order=work_order, project=project)


@app.route('/projects/<int:project_id>/document/<int:document_id>/delete', methods=['POST'])
@login_required
def delete_project_document(project_id, document_id):
    """Delete a project document"""
    document = WorkOrderDocument.query.get_or_404(document_id)
    
    # Verify the document belongs to this project
    if document.project_id != project_id:
        return "Invalid document", 400
        
    # Store information for logging
    doc_name = document.original_filename
    
    # Delete the document
    db.session.delete(document)
    
    # Log the deletion
    log_change(
        session.get('user_id'), 
        "Deleted Project Document", 
        "WorkOrderDocument",
        document_id,
        f"Deleted document '{doc_name}' from project"
    )
    
    db.session.commit()
    
    return redirect(url_for('project_detail', project_id=project_id))


# =============================================================================
# PROJECT TASK ROUTES
# =============================================================================
@app.route('/projects/<int:project_id>/task/new', methods=['GET', 'POST'])
@login_required
def new_task(project_id):
    """Create a new task in a project"""
    project = Project.query.get_or_404(project_id)
    
    # Get all users for the dropdown
    users = User.query.order_by(User.full_name).all()
    
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        start_date = parse_date(request.form.get('start_date'))
        end_date = parse_date(request.form.get('end_date'))
        estimated_hours = float(request.form.get('estimated_hours') or 0)
        priority = request.form.get('priority')
        dependencies = request.form.get('dependencies')
        assigned_to = request.form.get('assigned_to')
        
        new_task = ProjectTask(
            project_id=project_id,
            name=name,
            description=description,
            start_date=start_date,
            end_date=end_date,
            estimated_hours=estimated_hours,
            priority=priority,
            dependencies=dependencies,
            assigned_to=assigned_to
        )
        db.session.add(new_task)
        db.session.commit()
        
        # Log the creation
        log_change(session.get('user_id'), "Created Task", "ProjectTask", new_task.id,
                   f"Created task '{name}' for Project #{project_id}")
        db.session.commit()
        
        return redirect(url_for('project_detail', project_id=project_id))
        
    return render_template('new_task.html', project=project, existing_tasks=project.tasks, users=users)


@app.route('/projects/<int:project_id>/quick_add_task', methods=['POST'])
@login_required
def quick_add_task(project_id):
    """Quickly add a task to a project"""
    project = Project.query.get_or_404(project_id)
    
    try:
        # Get form data
        name = request.form.get('name')
        start_date = parse_date(request.form.get('start_date'))
        end_date = parse_date(request.form.get('end_date'))
        estimated_hours = float(request.form.get('estimated_hours') or 0)
        priority = request.form.get('priority', 'Medium')
        assigned_to = request.form.get('assigned_to', '')
        
        # Create new task
        new_task = ProjectTask(
            project_id=project_id,
            name=name,
            description="",  # Empty description for quick add
            start_date=start_date,
            end_date=end_date,
            estimated_hours=estimated_hours,
            status="Not Started",  # Default status
            priority=priority,
            assigned_to=assigned_to
        )
        
        # Get the highest position value for tasks in this project
        highest_position = db.session.query(db.func.max(ProjectTask.position)).filter_by(project_id=project_id).scalar() or 0
        new_task.position = highest_position + 1
        
        db.session.add(new_task)
        
        # Log the creation
        log_change(
            session.get('user_id'),
            "Created Task via Quick Add",
            "ProjectTask",
            None,  # Will be updated after commit
            f"Quick added task '{name}' for Project #{project_id}"
        )
        
        db.session.commit()
        
        # Update the log entry with the new task's ID
        log_entry = ChangeLog.query.filter_by(
            action="Created Task via Quick Add",
            object_type="ProjectTask",
            description=f"Quick added task '{name}' for Project #{project_id}"
        ).order_by(ChangeLog.timestamp.desc()).first()
        
        if log_entry:
            log_entry.object_id = new_task.id
            db.session.commit()
        
        # Check if this is an AJAX request
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': True,
                'task_id': new_task.id,
                'name': new_task.name
            })
        
        # If not AJAX, redirect to the project detail page
        return redirect(url_for('project_detail', project_id=project_id))
        
    except Exception as e:
        db.session.rollback()
        
        # If AJAX request, return JSON error
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': False,
                'error': str(e)
            }), 400
            
        # If not AJAX, redirect with error
        flash(f"Error creating task: {str(e)}", "error")
        return redirect(url_for('project_detail', project_id=project_id))


@app.route('/projects/tasks/<int:task_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_task(task_id):
    """Edit a project task"""
    task = ProjectTask.query.get_or_404(task_id)
    project = task.project
    
    # Get all users for the dropdown
    users = User.query.order_by(User.full_name).all()
    
    if request.method == 'POST':
        task.name = request.form.get('name')
        task.description = request.form.get('description')
        task.start_date = parse_date(request.form.get('start_date'))
        task.end_date = parse_date(request.form.get('end_date'))
        task.estimated_hours = float(request.form.get('estimated_hours') or 0)
        task.status = request.form.get('status')
        task.priority = request.form.get('priority')
        task.dependencies = request.form.get('dependencies')
        task.assigned_to = request.form.get('assigned_to')
        
        # Get and set the progress percentage
        progress_percent = request.form.get('progress_percent')
        if progress_percent is not None:
            try:
                task.progress_percent = int(progress_percent)
            except ValueError:
                # If conversion fails, don't update the field
                pass
                
        # If status is completed, ensure progress is 100%
        if task.status == 'Completed':
            task.progress_percent = 100
        
        db.session.commit()
        
        # Log the edit
        log_change(session.get('user_id'), "Edited Task", "ProjectTask", task.id,
                   f"Edited task '{task.name}' for Project #{project.id}")
        db.session.commit()
        
        return redirect(url_for('project_detail', project_id=project.id))
        
    return render_template('edit_task.html', task=task, project=project, existing_tasks=project.tasks, users=users)


@app.route('/projects/tasks/<int:task_id>/update_hours', methods=['POST'])
@login_required
def update_task_hours(task_id):
    """Update task hours and create time entry"""
    task = ProjectTask.query.get_or_404(task_id)
    project = task.project
    actual_hours = float(request.form.get('actual_hours') or 0)
    
    # Check if this is the first time hours are being added
    is_first_time_entry = task.actual_hours == 0 and actual_hours > 0
    
    # Update task hours
    task.actual_hours += actual_hours
    
    # Update task status based on completion if needed
    if task.actual_hours >= task.estimated_hours and task.status != 'Completed':
        task.status = 'Completed'
    # If this is the first time hours are being logged and status is 'Not Started', set to 'In Progress'
    elif is_first_time_entry and task.status == 'Not Started':
        task.status = 'In Progress'
        log_change(session.get('user_id'), "Updated Task Status", "ProjectTask", task.id,
                  f"Automatically updated task '{task.name}' status to 'In Progress' after logging first hours")
    
    # Add a time entry for this work
    if actual_hours > 0:
        # Create a time entry linked to both the work order and the task
        engineer = request.form.get('engineer')
        work_date = parse_date(request.form.get('work_date'))
        description = request.form.get('description') or f"Work on task: {task.name}"
        
        # Calculate time_in and time_out based on hours
        time_in_str = request.form.get('time_in')
        time_out_str = request.form.get('time_out')
        time_in = parse_time(time_in_str)
        time_out = parse_time(time_out_str)
        actual_hours = calculate_hours(work_date, time_in, time_out)  # Recalculate from times
        
        time_entry = TimeEntry(
            work_order_id=project.work_order_id,
            task_id=task.id,  # Link to task
            engineer=engineer,
            work_date=work_date,
            time_in=time_in,
            time_out=time_out,
            hours_worked=actual_hours,
            description=description
        )
        db.session.add(time_entry)
    
    db.session.commit()
    
    # Log the hours update
    log_change(session.get('user_id'), "Updated Task Hours", "ProjectTask", task.id,
               f"Added {actual_hours} hours to task '{task.name}' for Project #{project.id}")
    db.session.commit()
    
    return redirect(url_for('project_detail', project_id=project.id))


@app.route('/projects/tasks/<int:task_id>/reset_hours', methods=['POST'])
@login_required
def reset_task_hours(task_id):
    """Reset hours for a task"""
    task = ProjectTask.query.get_or_404(task_id)
    project = task.project
    
    # Get the submitted actual hours value
    new_actual_hours = float(request.form.get('actual_hours') or 0)
    
    # Update the task's actual hours
    task.actual_hours = new_actual_hours
    
    # Log the hours update
    log_change(
        session.get('user_id'),
        "Reset Task Hours",
        "ProjectTask",
        task.id,
        f"Reset hours for task '{task.name}' from {task.actual_hours} to {new_actual_hours}"
    )
    
    db.session.commit()
    
    return redirect(url_for('project_detail', project_id=project.id))


@app.route('/projects/tasks/<int:task_id>/delete', methods=['POST'])
@login_required
def delete_task(task_id):
    """Delete a task"""
    task = ProjectTask.query.get_or_404(task_id)
    project_id = task.project_id
    task_name = task.name
    
    # Check if there are any time entries associated with this task
    time_entries = TimeEntry.query.filter_by(task_id=task_id).all()
    
    # For each time entry, remove the task_id reference (don't delete the time entries)
    for entry in time_entries:
        entry.task_id = None
    
    # Delete the task
    db.session.delete(task)
    
    # Log the deletion
    log_change(
        session.get('user_id'),
        "Deleted Task",
        "ProjectTask",
        task_id,
        f"Deleted task '{task_name}' from Project #{project_id}"
    )
    
    db.session.commit()
    
    return redirect(url_for('project_detail', project_id=project_id))


@app.route('/projects/tasks/<int:task_id>/time_entries')
@login_required
def task_time_entries(task_id):
    """View time entries for a task"""
    task = ProjectTask.query.get_or_404(task_id)
    project = task.project
    work_order = project.work_order
    
    # Get time entries directly linked to this task
    task_entries = TimeEntry.query.filter_by(task_id=task_id).order_by(TimeEntry.work_date.desc()).all()
    
    # Get unassigned time entries from the work order
    unassigned_entries = TimeEntry.query.filter_by(
        work_order_id=work_order.id, 
        task_id=None
    ).order_by(TimeEntry.work_date.desc()).all()
    
    # Get default engineer and today's date
    default_engineer = ""
    if session.get('user_id'):
        current_user = User.query.get(session.get('user_id'))
        if current_user:
            default_engineer = get_engineer_name(current_user.username)
    
    today_date = datetime.now().strftime('%Y-%m-%d')
    
    return render_template(
        'task_time_entries.html',
        task=task,
        project=project,
        work_order=work_order,
        task_entries=task_entries,
        unassigned_entries=unassigned_entries,
        default_engineer=default_engineer,
        today_date=today_date
    )


@app.route('/time_entry/<int:entry_id>/assign_to_task/<int:task_id>', methods=['POST'])
@login_required
def assign_time_entry_to_task(entry_id, task_id):
    """Assign a time entry to a task"""
    entry = TimeEntry.query.get_or_404(entry_id)
    task = ProjectTask.query.get_or_404(task_id)
    project = task.project
    
    # Make sure the time entry belongs to the same work order as the task's project
    if entry.work_order_id != project.work_order_id:
        error_msg = "Time entry does not belong to this project's work order"
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': error_msg}), 400
        flash(error_msg, "danger")
        return redirect(url_for('task_time_entries', task_id=task_id))
    
    # Assign the time entry to the task
    entry.task_id = task.id
    
    # Update the task's actual hours
    task.actual_hours += entry.hours_worked
    
    # Update task status if needed
    if task.actual_hours >= task.estimated_hours and task.status != 'Completed':
        task.status = 'In Progress'
    
    db.session.commit()
    
    # Log the assignment
    log_change(
        session.get('user_id'),
        "Assigned Time Entry",
        "TimeEntry",
        entry.id,
        f"Assigned time entry #{entry.id} to task '{task.name}' in project #{project.id}"
    )
    db.session.commit()
    
    # Check if this is an AJAX request
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'success': True,
            'entry_id': entry.id,
            'task_id': task.id,
            'actual_hours': task.actual_hours,
            'hours_remaining': task.hours_remaining
        })
    
    # If not AJAX, use the standard redirect
    next_page = request.args.get('next') or url_for('task_time_entries', task_id=task.id)
    flash("Time entry assigned to task successfully.", "success")
    return redirect(next_page)




@app.route('/time_entry/<int:entry_id>/remove_from_task/<int:task_id>', methods=['POST'])
@login_required
def remove_time_entry_from_task(entry_id, task_id):
    """Remove a time entry from a task"""
    entry = TimeEntry.query.get_or_404(entry_id)
    task = ProjectTask.query.get_or_404(task_id)
    
    # Make sure the time entry is actually assigned to this task
    if entry.task_id != task.id:
        error_msg = "Time entry not assigned to this task"
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': error_msg}), 400
        return error_msg, 400
    
    # Subtract hours from the task's actual hours
    task.actual_hours -= entry.hours_worked
    if task.actual_hours < 0:
        task.actual_hours = 0
    
    # Unassign the time entry from the task
    entry.task_id = None
    
    db.session.commit()
    
    # Log the removal
    log_change(
        session.get('user_id'),
        "Removed Time Entry",
        "TimeEntry",
        entry.id,
        f"Removed time entry #{entry.id} from task '{task.name}'"
    )
    db.session.commit()
    
    # Check if this is an AJAX request
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'success': True,
            'entry_id': entry.id,
            'task_id': task.id,
            'actual_hours': task.actual_hours,
            'hours_remaining': task.hours_remaining
        })
    
    # If not AJAX, use the standard redirect
    return redirect(url_for('task_time_entries', task_id=task.id))


# =============================================================================
# GANTT CHART ROUTES
# =============================================================================
@app.route('/projects/<int:project_id>/gantt')
@login_required
def project_gantt(project_id):
    """View the Gantt chart for a project"""
    project = Project.query.get_or_404(project_id)
    return render_template('project_gantt.html', project=project)


@app.route('/api/projects/<int:project_id>/gantt_data')
@login_required
def project_gantt_data(project_id):
    """API endpoint to provide data for the Gantt chart"""
    project = Project.query.get_or_404(project_id)
    
    # Get tasks ordered by position field
    tasks = ProjectTask.query.filter_by(project_id=project_id).order_by(ProjectTask.position).all()
    
    # Debug information
    print(f"Project: {project.name}, Tasks count: {len(tasks)}")
    
    # Prepare data in DHTMLX Gantt format
    data = []
    links = []
    link_id = 1
    
    for task in tasks:
        # Skip tasks without dates
        if not task.start_date or not task.end_date:
            continue
            
        # Calculate duration in days
        duration = (task.end_date - task.start_date).days
        if duration <= 0:
            duration = 1  # Minimum duration is 1 day
        
        # Format task for Gantt chart - round progress to 2 decimal places
        progress_value = round(task.completion_percentage / 100, 2)
        
        task_data = {
            "id": task.id,
            "text": task.name,
            "start_date": task.start_date.strftime('%Y-%m-%d'),
            "duration": duration,
            "progress": progress_value,  # Rounded to 2 decimal places
            "status": task.status,
            "open": True,
            "sort_order": task.position  # Include position for reference
        }
        
        # Add custom data if needed
        if task.description:
            task_data["description"] = task.description
        if task.assigned_to:
            task_data["assigned_to"] = task.assigned_to
            
        data.append(task_data)
        
        # Add dependency links if any
        if task.dependencies:
            try:
                dependency_ids = [int(dep.strip()) for dep in task.dependencies.split(',') if dep.strip()]
                
                for dep_id in dependency_ids:
                    links.append({
                        "id": link_id,
                        "source": dep_id,
                        "target": task.id,
                        "type": "0"  # Finish-to-Start dependency type
                    })
                    link_id += 1
            except Exception as e:
                print(f"Error processing dependencies for task {task.id}: {e}")
    
    # Log the data we're returning
    print(f"Returning {len(data)} tasks and {len(links)} links")
    
    # Return the data in the format expected by DHTMLX Gantt
    return jsonify({
        "data": data,
        "links": links
    })


@app.route('/api/projects/<int:project_id>/reorder_tasks', methods=['POST'])
@login_required
def reorder_project_tasks(project_id):
    """API endpoint to save the new order of tasks after drag and drop"""
    project = Project.query.get_or_404(project_id)
    
    # Get data from request
    data = request.json
    task_id = data.get('task_id')
    new_index = data.get('new_index')
    tasks_order = data.get('tasks_order')
    
    if not all([task_id, isinstance(new_index, int), tasks_order]):
        return jsonify({'success': False, 'error': 'Invalid data provided'}), 400
    
    try:
        # Get the task that was moved
        task = ProjectTask.query.get_or_404(task_id)
        
        # Update the positions of all tasks in the project according to their new order
        for i, task_id in enumerate(tasks_order):
            current_task = ProjectTask.query.get(task_id)
            if current_task and current_task.project_id == project_id:
                current_task.position = i
        
        # Log the reordering
        log_change(
            session.get('user_id'),
            "Reordered Tasks",
            "Project",
            project_id,
            f"Reordered task '{task.name}' to position {new_index} in project '{project.name}'"
        )
        
        db.session.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    

@app.route('/api/projects/<int:project_id>/create_task', methods=['POST'])
@login_required
def create_task_from_gantt(project_id):
    """API endpoint to create a new task from the Gantt chart view"""
    project = Project.query.get_or_404(project_id)
    
    try:
        # Get task data from request
        data = request.json
        task_name = data.get('text', 'New Task')  # Task name/text
        start_date_str = data.get('start_date')
        duration = int(data.get('duration', 1))
        
        # Convert start_date to datetime
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else date.today()
        
        # Calculate end_date based on duration
        end_date = start_date + timedelta(days=duration)
        
        # Create new task
        new_task = ProjectTask(
            project_id=project_id,
            name=task_name,
            description="Created from Gantt chart",
            start_date=start_date,
            end_date=end_date,
            estimated_hours=8.0,  # Default estimated hours
            priority="Medium",  # Default priority
            status="Not Started"  # Default status
        )
        
        # Get the highest position value for tasks in this project
        highest_position = db.session.query(db.func.max(ProjectTask.position)).filter_by(project_id=project_id).scalar() or 0
        new_task.position = highest_position + 1
        
        db.session.add(new_task)
        
        # Log the creation
        log_change(
            session.get('user_id'),
            "Created Task from Gantt",
            "ProjectTask",
            None,  # Will be updated after commit
            f"Created task '{task_name}' from Gantt chart for Project #{project_id}"
        )
        
        db.session.commit()
        
        # Update the log entry with the new task's ID
        log_entry = ChangeLog.query.filter_by(
            action="Created Task from Gantt",
            object_type="ProjectTask",
            description=f"Created task '{task_name}' from Gantt chart for Project #{project_id}"
        ).order_by(ChangeLog.timestamp.desc()).first()
        
        if log_entry:
            log_entry.object_id = new_task.id
            db.session.commit()
        
        # Return the created task with its ID
        return jsonify({
            'success': True,
            'id': new_task.id,
            'text': new_task.name,
            'start_date': new_task.start_date.strftime('%Y-%m-%d'),
            'duration': duration,
            'progress': 0
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/tasks/<int:task_id>/update', methods=['POST'])
@login_required
def update_task_from_gantt(task_id):
    """API endpoint to update a task from the Gantt chart view"""
    task = ProjectTask.query.get_or_404(task_id)
    
    try:
        # Get data from request
        data = request.json
        
        # Update task properties
        if 'text' in data:
            task.name = data['text']
        
        if 'start_date' in data:
            task.start_date = datetime.strptime(data['start_date'], '%Y-%m-%d').date()
        
        if 'duration' in data and task.start_date:
            # Calculate end_date based on duration
            task.end_date = task.start_date + timedelta(days=int(data['duration']))
        
        if 'progress' in data:
            # Convert progress (0-1) to percentage (0-100)
            progress_percentage = int(float(data['progress']) * 100)
            task.progress_percent = progress_percentage
            
            # Update status based on progress if appropriate
            if progress_percentage == 100 and task.status != 'Completed':
                task.status = 'Completed'
            elif progress_percentage > 0 and task.status == 'Not Started':
                task.status = 'In Progress'
                
        # Log the update
        log_change(
            session.get('user_id'),
            "Updated Task from Gantt",
            "ProjectTask",
            task.id,
            f"Updated task '{task.name}' from Gantt chart"
        )
        
        db.session.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# =============================================================================
# ADMIN ROUTES
# =============================================================================
@app.route('/admin/users')
@login_required
@admin_required
def admin_users():
    """Admin page to manage users"""
    users = User.query.all()
    return render_template('admin_users.html', users=users)


@app.route('/admin/users/new', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_new_user():
    """Create a new user"""
    if request.method == 'POST':
        username = request.form.get('username').strip()
        password = request.form.get('password')
        role = request.form.get('role', 'user').strip().lower()
        full_name = request.form.get('full_name', '').strip()
        
        # Force the role to "admin" if the username is "admin"
        if username.lower() == "admin":
            role = "admin"
        
        # Check for duplicate username
        if User.query.filter_by(username=username).first():
            return "User already exists", 400
        
        new_user = User(username=username, role=role, full_name=full_name)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        return redirect(url_for('admin_users'))
    return render_template('admin_new_user.html')


@app.route('/admin/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_edit_user(user_id):
    """Edit a user"""
    user = User.query.get_or_404(user_id)
    if request.method == 'POST':
        username = request.form.get('username').strip()
        full_name = request.form.get('full_name', '').strip()
        
        # If editing the admin account, force role to "admin"
        if username.lower() == "admin":
            role = "admin"
        else:
            role = request.form.get('role', 'user').strip().lower()
        new_password = request.form.get('password')
        
        user.username = username
        user.role = role
        user.full_name = full_name
        if new_password:
            user.set_password(new_password)
        db.session.commit()
        return redirect(url_for('admin_users'))
    return render_template('admin_edit_user.html', user=user)


@app.route('/admin/users/<int:user_id>/delete', methods=['POST'])
@login_required
@admin_required
def admin_delete_user(user_id):
    """Delete a user"""
    user = User.query.get_or_404(user_id)
    # Prevent deletion of the admin account itself.
    if user.username.lower() == "admin":
        return "Cannot delete admin user", 403
    db.session.delete(user)
    db.session.commit()
    return redirect(url_for('admin_users'))


@app.route('/admin/users/<int:user_id>/update_role', methods=['POST'])
@login_required
@admin_required
def admin_update_user_role(user_id):
    """Update a user's role"""
    user = User.query.get_or_404(user_id)
    new_role = request.form.get('role', 'user').lower()  # Ensure lowercase
    
    # Force admin account to remain admin
    if user.username.lower() == 'admin':
        new_role = 'admin'
    
    # Set and commit role change
    user.role = new_role
    db.session.commit()
    
    # If updating own role, refresh session
    if user_id == session.get('user_id'):
        # You may need to refresh the session
        session['user_role'] = new_role  # Add role to session
        
    return redirect(url_for('admin_users'))


@app.route('/admin/changelog')
@login_required
@admin_required
def admin_changelog():
    """View the change log"""
    logs = ChangeLog.query.order_by(ChangeLog.timestamp.desc()).all()
    return render_template('admin_changelog.html', logs=logs)


@app.route('/admin/email_settings', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_email_settings():
    """Manage email notification settings"""
    if request.method == 'POST':
        # Process global notification settings
        global_enabled = 'notification_enabled' in request.form
        default_email = request.form.get('default_notification_email', '')
        
        # Debug output - before processing
        print("==== FORM DATA RECEIVED ====")
        for key, value in request.form.items():
            print(f"{key}: {value}")
        
        # Update all notification types
        notification_types = [
            'report_upload', 'report_approval', 'status_change', 
            'hours_threshold', 'scheduled_date', 'new_work_order'
        ]
        
        # Update each notification type
        for notification_type in notification_types:
            setting = NotificationSetting.query.filter_by(notification_type=notification_type).first()
            if not setting:
                # Create if it doesn't exist
                setting = NotificationSetting(notification_type=notification_type)
                db.session.add(setting)
            
            # Only enable if global notifications are enabled and this type is checked
            type_enabled = f'{notification_type}_enabled' in request.form
            setting.enabled = global_enabled and type_enabled
            
            # Get or create options dictionary
            options = {}
            
            # Process type-specific options
            if notification_type == 'report_upload':
                keywords = request.form.get('report_keywords', '')
                options['report_keywords'] = [k.strip() for k in keywords.split(',') if k.strip()]
            
            elif notification_type == 'report_approval':
                options['send_reminder'] = 'report_approval_reminder' in request.form
                options['reminder_days'] = int(request.form.get('report_approval_reminder_days', 3))
            
            elif notification_type == 'status_change':
                options['open_to_complete'] = 'status_open_to_complete' in request.form
                options['complete_to_closed'] = 'status_complete_to_closed' in request.form
                options['any_to_open'] = 'status_any_to_open' in request.form
            
            elif notification_type == 'hours_threshold':
                options['warning_threshold'] = int(request.form.get('hours_warning_threshold', 80))
                options['exceeded_alert'] = 'hours_exceeded_alert' in request.form
                options['include_work_order_owner'] = 'include_work_order_owner' in request.form
            
            elif notification_type == 'scheduled_date':
                options['days_before'] = int(request.form.get('scheduled_date_days', 3))
                options['include_owner'] = 'scheduled_include_owner' in request.form
            
            elif notification_type == 'new_work_order':
                options['high_priority'] = 'new_work_order_high' in request.form
                options['medium_priority'] = 'new_work_order_medium' in request.form
                options['low_priority'] = 'new_work_order_low' in request.form
            
            setting.options = options
            
            # Update recipients for this notification type
            # FIXED: Use the format that's actually coming from the form
            recipient_key = f"{notification_type}_recipients"
            recipient_emails = request.form.getlist(recipient_key)
            
            print(f"Recipients for {notification_type}: {recipient_emails}")
            
            # Clear existing recipients
            NotificationRecipient.query.filter_by(notification_setting_id=setting.id).delete()
            
            # Add new recipients
            for email in recipient_emails:
                if email and '@' in email:
                    recipient = NotificationRecipient(
                        notification_setting_id=setting.id,
                        email=email.strip()
                    )
                    db.session.add(recipient)
        
        # Store the default email in app config for redundancy
        app.config['REPORT_NOTIFICATION_EMAIL'] = default_email
        app.config['REPORT_NOTIFICATION_ENABLED'] = global_enabled
        
        db.session.commit()
        flash('Email settings updated successfully', 'success')
        
        # CHANGE: Don't redirect, continue to load the template with fresh data
    
    # Prepare data for the template - will be used for both GET and after POST
    notification_settings = {}
    report_keywords_list = []
    
    # Load settings from database
    for setting in NotificationSetting.query.all():
        notification_settings[setting.notification_type] = {
            'enabled': setting.enabled,
            'options': setting.options,
            'recipients': [r.email for r in setting.recipients]
        }
        
        # Extract report keywords for the template
        if setting.notification_type == 'report_upload' and setting.options and 'report_keywords' in setting.options:
            report_keywords_list = setting.options['report_keywords']
    
    # Get global enabled status from report_upload setting
    global_enabled = False
    report_upload = NotificationSetting.query.filter_by(notification_type='report_upload').first()
    if report_upload:
        global_enabled = report_upload.enabled
    
    # Prepare template data with values from database
    template_data = {
        'notification_enabled': global_enabled,
        'notification_email': app.config.get('REPORT_NOTIFICATION_EMAIL', ''),
        'mail_server': app.config.get('MAIL_SERVER', ''),
        'mail_port': app.config.get('MAIL_PORT', 587),
        'mail_use_tls': app.config.get('MAIL_USE_TLS', True),
        'mail_username': app.config.get('MAIL_USERNAME', ''),
        'report_keywords': ','.join(report_keywords_list),
        'settings': notification_settings
    }
    
    # Debug output - what's being sent to template
    print("==== TEMPLATE DATA ====")
    print(f"notification_enabled: {template_data['notification_enabled']}")
    print(f"notification_email: {template_data['notification_email']}")
    print(f"report_keywords: {template_data['report_keywords']}")
    print("Settings:")
    for key, value in notification_settings.items():
        print(f"  {key}: enabled={value['enabled']}, recipients={value['recipients']}")
    
    return render_template('admin_email_settings.html', **template_data)

@app.route('/admin/dashboard')
@login_required
@admin_required
def admin_dashboard():
    """Admin dashboard with analytics"""
    try:
        # Get time frame from request parameters, default to last 30 days
        time_frame = request.args.get('time_frame', 'month')
        
        # Calculate start and end dates based on time frame
        end_date = datetime.now().date()
        if time_frame == 'week':
            start_date = end_date - timedelta(days=7)
        elif time_frame == 'month':
            start_date = end_date - timedelta(days=30)
        elif time_frame == 'quarter':
            start_date = end_date - timedelta(days=90)
        elif time_frame == 'year':
            start_date = end_date - timedelta(days=365)
        else:
            # Custom date range
            start_date_str = request.args.get('start_date')
            end_date_str = request.args.get('end_date')
            start_date = parse_date(start_date_str) or (end_date - timedelta(days=30))
            end_date = parse_date(end_date_str) or end_date
        
        # Get all time entries in the selected time period
        time_entries = TimeEntry.query.filter(
            TimeEntry.work_date >= start_date,
            TimeEntry.work_date <= end_date
        ).all()
        
        # Get all work orders associated with these time entries
        work_order_ids = set(entry.work_order_id for entry in time_entries if entry.work_order_id is not None)
        work_orders = WorkOrder.query.filter(WorkOrder.id.in_(work_order_ids)).all() if work_order_ids else []
        
        # Create a mapping of work order ID to classification
        work_order_classification = {}
        for wo in work_orders:
            # If classification field exists
            if hasattr(wo, 'classification') and wo.classification is not None:
                classification = wo.classification
            else:
                # Temporary classification logic based on existing fields
                if wo.customer_work_order_number and wo.customer_work_order_number.strip():
                    classification = 'Contract/Project'
                elif wo.description and ('internal' in wo.description.lower() or 'non-billable' in wo.description.lower()):
                    classification = 'Non-Billable'
                else:
                    classification = 'Billable'
            work_order_classification[wo.id] = classification
        
        # Get all engineers who have time entries in the selected period
        engineers = sorted(list(set(entry.engineer for entry in time_entries if entry.engineer is not None)))
        
        # Initialize data structures
        engineer_hours = {engineer: 0 for engineer in engineers}
        classification_hours = {'Contract/Project': 0, 'Billable': 0, 'Non-Billable': 0}
        engineer_classification_hours = {
            engineer: {'Contract/Project': 0, 'Billable': 0, 'Non-Billable': 0} 
            for engineer in engineers
        }
        
        # Calculate hours by engineer and classification
        for entry in time_entries:
            if entry.engineer is None or entry.work_order_id is None:
                continue
                
            engineer = entry.engineer
            classification = work_order_classification.get(entry.work_order_id, 'Billable')
            
            engineer_hours[engineer] += entry.hours_worked
            classification_hours[classification] += entry.hours_worked
            engineer_classification_hours[engineer][classification] += entry.hours_worked
        
        # Calculate percentages
        total_hours = sum(engineer_hours.values())
        engineer_percentage = {eng: (hrs/total_hours*100 if total_hours > 0 else 0) 
                              for eng, hrs in engineer_hours.items()}
        classification_percentage = {cls: (hrs/total_hours*100 if total_hours > 0 else 0) 
                                    for cls, hrs in classification_hours.items()}
        
        # Get daily/weekly data for timeline chart
        timeline_data = {}
        if time_frame in ['week', 'month']:
            # Daily aggregation for week or month view
            for i in range((end_date - start_date).days + 1):
                current_date = start_date + timedelta(days=i)
                timeline_data[current_date.strftime('%Y-%m-%d')] = 0
                
            for entry in time_entries:
                if entry.work_date:
                    date_key = entry.work_date.strftime('%Y-%m-%d')
                    if date_key in timeline_data:
                        timeline_data[date_key] += entry.hours_worked
        else:
            # Weekly aggregation for quarter or year view
            current_week_start = start_date - timedelta(days=start_date.weekday())
            while current_week_start <= end_date:
                week_end = current_week_start + timedelta(days=6)
                week_key = f"{current_week_start.strftime('%b %d')} - {week_end.strftime('%b %d')}"
                timeline_data[week_key] = 0
                current_week_start += timedelta(days=7)
                
            for entry in time_entries:
                if entry.work_date:
                    entry_week_start = entry.work_date - timedelta(days=entry.work_date.weekday())
                    entry_week_end = entry_week_start + timedelta(days=6)
                    week_key = f"{entry_week_start.strftime('%b %d')} - {entry_week_end.strftime('%b %d')}"
                    if week_key in timeline_data:
                        timeline_data[week_key] += entry.hours_worked
        
        # Prepare chart data in JSON format
        chart_data = {
            'engineers': list(engineer_hours.keys()),
            'engineerHours': list(engineer_hours.values()),
            'engineerPercentage': list(engineer_percentage.values()),
            'classifications': list(classification_hours.keys()),
            'classificationHours': list(classification_hours.values()),
            'classificationPercentage': list(classification_percentage.values()),
            'timelineLabels': list(timeline_data.keys()),
            'timelineData': list(timeline_data.values()),
            'engineerClassificationData': engineer_classification_hours
        }
        
        return render_template(
            'admin_dashboard.html',
            time_frame=time_frame,
            start_date=start_date,
            end_date=end_date,
            chart_data=chart_data,
            total_hours=total_hours
        )
    
    except Exception as e:
        # Log the exception
        print(f"Error in admin_dashboard: {e}")
        
        # Return an error page or a simplified dashboard with no data
        return render_template(
            'admin_dashboard.html',
            time_frame='month',
            start_date=datetime.now().date() - timedelta(days=30),
            end_date=datetime.now().date(),
            chart_data={
                'engineers': [],
                'engineerHours': [],
                'engineerPercentage': [],
                'classifications': ['Contract/Project', 'Billable', 'Non-Billable'],
                'classificationHours': [0, 0, 0],
                'classificationPercentage': [0, 0, 0],
                'timelineLabels': [],
                'timelineData': [],
                'engineerClassificationData': {}
            },
            total_hours=0,
            error_message=f"An error occurred: {str(e)}"
        )


@app.route('/admin/classify_work_orders', methods=['GET', 'POST'])
@login_required
@admin_required
def classify_work_orders():
    """Bulk classify work orders"""
    message = None
    if request.method == 'POST':
        # Get all work orders
        work_orders = WorkOrder.query.all()
        
        # Initialize counters
        billable_count = 0
        non_billable_count = 0
        skipped_count = 0
        
        # Process each work order
        for work_order in work_orders:
            customer_wo = work_order.customer_work_order_number
            rmj_job = work_order.rmj_job_number
            
            # Check if it's already classified
            if hasattr(work_order, 'classification') and work_order.classification:
                if work_order.classification == 'Contract/Project':
                    # Skip Contract/Project as requested
                    skipped_count += 1
                    continue
                    
            # Apply classification rules
            if customer_wo in ['0', '00', '000', '0000']:
                work_order.classification = 'Non-Billable'
                non_billable_count += 1
            elif customer_wo and rmj_job and len(customer_wo.strip()) == 6:
                work_order.classification = 'Billable'
                billable_count += 1
            else:
                # Default to Billable for anything else
                work_order.classification = 'Billable'
                billable_count += 1
        
        # Commit changes
        db.session.commit()
        
        # Log the operation
        log_change(
            session.get('user_id'),
            "Bulk Classification",
            "WorkOrder",
            None,
            f"Bulk classified work orders: {billable_count} as Billable, {non_billable_count} as Non-Billable, {skipped_count} skipped"
        )
        db.session.commit()
        
        message = f"Classification complete! {billable_count} work orders set as Billable, {non_billable_count} set as Non-Billable, {skipped_count} skipped (Contract/Project)."
        
    return render_template('admin_classify_work_orders.html', message=message)


@app.route('/admin/dashboard/engineer_entries/<engineer>')
@login_required
@admin_required
def get_engineer_entries(engineer):
    """Get time entries for a specific engineer"""
    try:
        # Get time frame from request parameters
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')
        
        # Parse dates or use defaults
        start_date = parse_date(start_date_str)
        end_date = parse_date(end_date_str)
        
        if not start_date or not end_date:
            return jsonify({'error': 'Invalid date parameters'}), 400
            
        # Query for this engineer's time entries in the date range
        entries = (TimeEntry.query
                  .filter(TimeEntry.engineer == engineer)
                  .filter(TimeEntry.work_date >= start_date)
                  .filter(TimeEntry.work_date <= end_date)
                  .order_by(TimeEntry.work_date.desc())
                  .all())
                  
        # Format the entries for JSON response
        result = []
        for entry in entries:
            # Get work order details
            work_order = WorkOrder.query.get(entry.work_order_id)
            classification = getattr(work_order, 'classification', 'Billable') if work_order else 'Billable'
            
            result.append({
                'id': entry.id,
                'engineer': entry.engineer if entry.engineer else engineer,
                'work_date': entry.work_date.strftime('%Y-%m-%d'),
                'time_in': entry.time_in.strftime('%H:%M'),
                'time_out': entry.time_out.strftime('%H:%M'),
                'hours_worked': round(entry.hours_worked, 2),
                'description': entry.description,
                'work_order': {
                    'id': work_order.id if work_order else None,
                    'rmj_job_number': work_order.rmj_job_number if work_order else 'N/A',
                    'customer_work_order_number': work_order.customer_work_order_number if work_order else 'N/A',
                    'description': work_order.description if work_order else 'N/A',
                    'classification': classification
                }
            })
            
        return jsonify({
            'engineer': engineer,
            'start_date': start_date.strftime('%Y-%m-%d'),
            'end_date': end_date.strftime('%Y-%m-%d'),
            'entries': result,
            'total_hours': sum(entry['hours_worked'] for entry in result)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/admin/dashboard/classification_entries/<classification>')
@login_required
@admin_required
def get_classification_entries(classification):
    """Get time entries for a specific classification"""
    try:
        # Get time frame from request parameters
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')
        
        # Parse dates or use defaults
        start_date = parse_date(start_date_str)
        end_date = parse_date(end_date_str)
        
        if not start_date or not end_date:
            return jsonify({'error': 'Invalid date parameters'}), 400
        
        # Subquery to get work orders with this classification
        if hasattr(WorkOrder, 'classification'):
            # If classification field exists
            work_orders = WorkOrder.query.filter_by(classification=classification).all()
        else:
            # Temporary classification logic
            if classification == 'Contract/Project':
                work_orders = WorkOrder.query.filter(
                    WorkOrder.customer_work_order_number.like('______'),  # 6 digits
                    WorkOrder.rmj_job_number.isnot(None)
                ).all()
            elif classification == 'Non-Billable':
                work_orders = WorkOrder.query.filter(
                    WorkOrder.customer_work_order_number.in_(['0', '00', '000', '0000'])
                ).all()
            else:  # Billable - default case
                work_orders = WorkOrder.query.filter(
                    ~WorkOrder.customer_work_order_number.in_(['0', '00', '000', '0000']),
                    ~WorkOrder.customer_work_order_number.like('______')
                ).all()
        
        work_order_ids = [wo.id for wo in work_orders]
        
        # Get all time entries for these work orders in the date range
        entries = []
        if work_order_ids:
            entries = (TimeEntry.query
                      .filter(TimeEntry.work_order_id.in_(work_order_ids))
                      .filter(TimeEntry.work_date >= start_date)
                      .filter(TimeEntry.work_date <= end_date)
                      .order_by(TimeEntry.work_date.desc())
                      .all())
        
        # Format the entries for JSON response
        result = []
        for entry in entries:
            # Get work order details
            work_order = WorkOrder.query.get(entry.work_order_id)
            
            result.append({
                'id': entry.id,
                'engineer': entry.engineer if entry.engineer else "Not Specified",  # Add fallback
                'work_date': entry.work_date.strftime('%Y-%m-%d'),
                'time_in': entry.time_in.strftime('%H:%M'),
                'time_out': entry.time_out.strftime('%H:%M'),
                'hours_worked': round(entry.hours_worked, 2),
                'description': entry.description,
                'work_order': {
                    'id': work_order.id if work_order else None,
                    'rmj_job_number': work_order.rmj_job_number if work_order else 'N/A',
                    'customer_work_order_number': work_order.customer_work_order_number if work_order else 'N/A',
                    'description': work_order.description if work_order else 'N/A',
                    'classification': classification  # Ensure classification is included
                }
            })
            
        return jsonify({
            'classification': classification,
            'start_date': start_date.strftime('%Y-%m-%d'),
            'end_date': end_date.strftime('%Y-%m-%d'),
            'entries': result,
            'total_hours': sum(entry['hours_worked'] for entry in result)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/dashboard/all_classification_entries')
@login_required
@admin_required
def get_all_classification_entries():
    """Get time entries for all classifications - client will filter by classification"""
    try:
        # Get time frame from request parameters
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')
        
        # Parse dates or use defaults
        start_date = parse_date(start_date_str)
        end_date = parse_date(end_date_str)
        
        if not start_date or not end_date:
            return jsonify({'error': 'Invalid date parameters'}), 400
        
        # Get all time entries for the period
        entries = (TimeEntry.query
                  .filter(TimeEntry.work_date >= start_date)
                  .filter(TimeEntry.work_date <= end_date)
                  .order_by(TimeEntry.work_date.desc())
                  .all())
                  
        # Format all entries for JSON response
        result = []
        for entry in entries:
            # Get work order details
            work_order = WorkOrder.query.get(entry.work_order_id)
            classification = getattr(work_order, 'classification', 'Billable') if work_order else 'Billable'
            
            result.append({
                'id': entry.id,
                'engineer': entry.engineer if entry.engineer else "Not Specified",
                'work_date': entry.work_date.strftime('%Y-%m-%d'),
                'time_in': entry.time_in.strftime('%H:%M'),
                'time_out': entry.time_out.strftime('%H:%M'),
                'hours_worked': round(entry.hours_worked, 2),
                'description': entry.description,
                'work_order': {
                    'id': work_order.id if work_order else None,
                    'rmj_job_number': work_order.rmj_job_number if work_order else 'N/A',
                    'customer_work_order_number': work_order.customer_work_order_number if work_order else 'N/A',
                    'description': work_order.description if work_order else 'N/A',
                    'classification': classification
                }
            })
            
        return jsonify({
            'start_date': start_date.strftime('%Y-%m-%d'),
            'end_date': end_date.strftime('%Y-%m-%d'),
            'entries': result,
            'total_hours': sum(entry['hours_worked'] for entry in result)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/bulk_delete_time_entries', methods=['GET', 'POST'])
@login_required
@admin_required
def bulk_delete_time_entries():
    """Bulk delete time entries"""
    message = None
    if request.method == 'POST':
        selected_ids = request.form.getlist('time_entry_ids')
        if not selected_ids:
            message = "No time entries selected."
        else:
            try:
                # Convert selected IDs to integers.
                ids = list(map(int, selected_ids))
            except Exception:
                message = "Error processing selected IDs."
            else:
                # Query for the time entries with the selected IDs.
                entries = TimeEntry.query.filter(TimeEntry.id.in_(ids)).all()
                count = len(entries)
                for entry in entries:
                    db.session.delete(entry)
                db.session.commit()
                message = f"Deleted {count} time entry record(s)."
    # On GET (or after deletion) show all time entries.
    time_entries = TimeEntry.query.order_by(TimeEntry.id).all()
    return render_template('admin_bulk_delete_time_entries.html', time_entries=time_entries, message=message)


@app.route('/admin/import_time_entries', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_import_time_entries():
    """Import time entries from Excel"""
    message = None
    if request.method == 'POST':
        if 'file' not in request.files:
            message = "No file part provided."
            return render_template('admin_import_time_entries.html', message=message)
            
        file = request.files['file']
        if file.filename == '':
            message = "No file selected."
            return render_template('admin_import_time_entries.html', message=message)
        
        try:
            # Load the entire workbook so we can iterate over its sheets.
            xls = pd.ExcelFile(file)
            count = 0  # Counter for the number of imported time entries

            # Process each sheet in the workbook.
            for sheet_name in xls.sheet_names:
                try:
                    # Read only the first 50 rows after the header row
                    df = pd.read_excel(xls, sheet_name=sheet_name, header=1, nrows=50)
                except ValueError:
                    continue

                if df.empty:
                    continue

                # Ensure required columns are present.
                required_columns = ['Engineer', 'Date:', 'WO#', 'Job Number', 'Hours']
                missing_cols = [col for col in required_columns if col not in df.columns]
                if missing_cols:
                    continue

                # Process each row in the current sheet.
                for index, row in df.iterrows():
                    # Retrieve and process the Job Number from the row.
                    job_number_raw = row.get("Job Number")
                    if pd.isna(job_number_raw):
                        continue

                    try:
                        if isinstance(job_number_raw, (int, float)):
                            job_number = str(int(job_number_raw))
                        else:
                            job_number = str(job_number_raw).strip()
                    except Exception:
                        continue

                    # Look up the work order using the Job Number.
                    work_order = WorkOrder.query.filter_by(rmj_job_number=job_number).first()
                    if not work_order:
                        continue

                    # Process the Engineer field.
                    engineer = row.get("Engineer")
                    if pd.isna(engineer):
                        continue

                    # Process the Date field.
                    date_value = row.get("Date:")
                    if pd.isna(date_value):
                        continue

                    try:
                        if isinstance(date_value, datetime):
                            work_date = date_value.date()
                        else:
                            work_date = pd.to_datetime(date_value).date()
                    except Exception:
                        continue

                    # Process the hours field.
                    hours = row.get("Hours")
                    if pd.isna(hours):
                        continue

                    try:
                        hours_float = float(hours)
                    except Exception:
                        continue

                    if hours_float <= 0:
                        continue  # Skip rows with zero or negative hours

                    # Set the time_in value to midnight.
                    time_in_value = time(0, 0)
                    # Calculate time_out by adding the hours worked.
                    time_out_dt = datetime.combine(work_date, time_in_value) + timedelta(hours=hours_float)
                    time_out_value = time_out_dt.time()

                    # Create and add the new TimeEntry record.
                    new_entry = TimeEntry(
                        work_order_id=work_order.id,
                        engineer=engineer,
                        work_date=work_date,
                        time_in=time_in_value,
                        time_out=time_out_value,
                        hours_worked=hours_float,
                        description="Imported time entry"
                    )
                    db.session.add(new_entry)
                    count += 1

            db.session.commit()
            message = f"Imported {count} time entry record(s)."
        except Exception as e:
            message = f"Error processing file: {str(e)}"
    
    return render_template('admin_import_time_entries.html', message=message)


# =============================================================================
# TIME ENTRY REASSIGNMENT ROUTES
# =============================================================================
@app.route('/workorder/reassign_entries', methods=['GET', 'POST'])
@login_required
@admin_required
def reassign_entries():
    """Reassign time entries from one work order to another"""
    if request.method == 'POST':
        source_id = request.form.get('source_work_order_id')
        target_id = request.form.get('target_work_order_id')
        if not source_id or not target_id:
            return "Please select both source and target work orders", 400
        entries = TimeEntry.query.filter_by(work_order_id=source_id).all()
        for entry in entries:
            entry.work_order_id = int(target_id)
        db.session.commit()
        return redirect(url_for('index'))
    else:
        work_orders = WorkOrder.query.all()
        return render_template('reassign_entries.html', work_orders=work_orders)


@app.route('/workorder/reassign_entries_selected', methods=['POST'])
@login_required
@admin_required
def reassign_entries_selected():
    """Selectively reassign specific time entries"""
    if request.method == 'POST':
        try:
            # Get target work order ID and entry IDs
            target_id = request.form.get('target_id')
            entries_json = request.form.get('entries_json')
            
            if not target_id or not entries_json:
                flash("Missing required parameters", "danger")
                return redirect(url_for('reassign_entries'))
            
            # Parse the entry IDs
            entry_ids = json.loads(entries_json)
            
            if not entry_ids:
                flash("No entries selected", "warning")
                return redirect(url_for('reassign_entries'))
            
            # Get all the time entries
            entries = TimeEntry.query.filter(TimeEntry.id.in_(entry_ids)).all()
            
            # Check if any entries are locked due to JL/JT checkboxes
            locked_entries = [entry for entry in entries if entry.entered_on_jl or entry.entered_on_jt]
            if locked_entries:
                locked_count = len(locked_entries)
                flash(f"Cannot reassign {locked_count} time entries: They have been entered into the accounting system (JL/JT checked).", "danger")
                return redirect(url_for('reassign_entries'))
            
            # Get the target work order
            target_work_order = WorkOrder.query.get_or_404(int(target_id))
            
            # Track source work order IDs for logging
            source_work_order_ids = set()
            
            # Update each entry
            for entry in entries:
                source_work_order_ids.add(entry.work_order_id)
                entry.work_order_id = int(target_id)
            
            # Commit the changes
            db.session.commit()
            
            # Log the reassignment
            source_ids_str = ", ".join(map(str, source_work_order_ids))
            log_change(
                session.get('user_id'),
                "Reassigned Time Entries",
                "TimeEntry",
                None,
                f"Reassigned {len(entries)} time entries from work order(s) {source_ids_str} to work order {target_id}"
            )
            db.session.commit()
            
            # Flash a success message
            flash(f"Successfully reassigned {len(entries)} time entries to work order {target_work_order.rmj_job_number}", "success")
            
            # Redirect to the target work order's detail page
            return redirect(url_for('work_order_detail', work_order_id=target_id))
            
        except Exception as e:
            # Log the error and show an error message
            print(f"Error in reassign_entries_selected: {e}")
            flash(f"Error reassigning time entries: {str(e)}", "danger")
            return redirect(url_for('index'))

    # If not POST, redirect to the main reassign entries page
    return redirect(url_for('reassign_entries'))


# =============================================================================
# API ROUTES
# =============================================================================
@app.route('/api/work_order/<int:work_order_id>/time_entries', methods=['GET'])
@login_required
def get_work_order_time_entries(work_order_id):
    """API endpoint to get time entries for a specific work order"""
    try:
        # Get the work order
        work_order = WorkOrder.query.get_or_404(work_order_id)
        
        # Get all time entries for this work order
        entries = TimeEntry.query.filter_by(work_order_id=work_order_id).all()
        
        # Format the entries for JSON response
        result = []
        for entry in entries:
            result.append({
                'id': entry.id,
                'work_order_id': entry.work_order_id,
                'engineer': entry.engineer,
                'work_date': entry.work_date.strftime('%Y-%m-%d'),
                'time_in': entry.time_in.strftime('%H:%M'),
                'time_out': entry.time_out.strftime('%H:%M'),
                'hours_worked': float(entry.hours_worked),
                'description': entry.description
            })
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# =============================================================================
# CONTEXT PROCESSORS
# =============================================================================
@app.context_processor
def inject_user_model():
    """Inject User model into all templates"""
    return dict(User=User)

@app.context_processor
def inject_datetime():
    from datetime import datetime, timedelta
    return {
        'datetime': datetime,
        'timedelta': timedelta,
        'today_date': datetime.now().date()
    }


# =============================================================================
# APP INITIALIZATION
# =============================================================================
# Initialize the database when the app starts
with app.app_context():
    populate_user_full_names()

# Add this to the APP INITIALIZATION section

def initialize_notification_settings():
    """Initialize default notification settings if they don't exist"""
    notification_types = [
        'report_upload', 'report_approval', 'status_change', 
        'hours_threshold', 'scheduled_date', 'new_work_order'
    ]
    
    for notification_type in notification_types:
        # Check if setting already exists
        setting = NotificationSetting.query.filter_by(notification_type=notification_type).first()
        if not setting:
            # Create default setting
            enabled = notification_type == 'report_upload'  # Only enable report upload by default
            default_options = {}
            
            # Set default options based on notification type
            if notification_type == 'report_upload':
                default_options = {
                    'report_keywords': ['report', 'assessment', 'evaluation']
                }
            elif notification_type == 'hours_threshold':
                default_options = {
                    'warning_threshold': 80,
                    'exceeded_alert': True,
                    'include_work_order_owner': True
                }
            elif notification_type == 'scheduled_date':
                default_options = {
                    'days_before': 3,
                    'include_owner': True
                }
            elif notification_type == 'status_change':
                default_options = {
                    'open_to_complete': True,
                    'complete_to_closed': True,
                    'any_to_open': False
                }
            elif notification_type == 'report_approval':
                default_options = {
                    'send_reminder': False,
                    'reminder_days': 3
                }
            elif notification_type == 'new_work_order':
                default_options = {
                    'high_priority': True,
                    'medium_priority': True,
                    'low_priority': False
                }
            
            new_setting = NotificationSetting(
                notification_type=notification_type,
                enabled=enabled,
                options=default_options
            )
            db.session.add(new_setting)
            
            # Add default recipient for report_upload if applicable
            if notification_type == 'report_upload' and 'REPORT_NOTIFICATION_EMAIL' in app.config:
                email = app.config['REPORT_NOTIFICATION_EMAIL']
                if email:
                    recipient = NotificationRecipient(
                        notification_setting=new_setting,
                        email=email
                    )
                    db.session.add(recipient)
    
    db.session.commit()
    print("Notification settings initialized")

# Add this to the app initialization
with app.app_context():
    db.create_all()
    populate_user_full_names()
    initialize_notification_settings()

def start_scheduler():
    """Start the background task scheduler"""
    import threading
    import time
    
    def run_scheduler():
        """Run scheduled tasks"""
        while True:
            try:
                with app.app_context():
                    # Check for scheduled date reminders every day
                    check_scheduled_date_reminders()
                    
                    # Check for report approval reminders
                    # This would check for reports that were uploaded but not approved
                    # and send reminders if necessary
                    
            except Exception as e:
                print(f"Error in scheduler: {e}")
            
            # Sleep for 1 hour before checking again
            time.sleep(3600)
    
    # Start the scheduler in a background thread
    scheduler_thread = threading.Thread(target=run_scheduler)
    scheduler_thread.daemon = True
    scheduler_thread.start()
    print("Scheduler started")

# Start the scheduler when the app starts
if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
    start_scheduler()


# Run the application if executed directly
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        # Add lunch_deduction column if it doesn't exist
        try:
            db.engine.execute("ALTER TABLE time_entry ADD COLUMN lunch_deduction FLOAT DEFAULT 0")
            print("Added lunch_deduction column")
        except:
            print("lunch_deduction column already exists or error occurred")
    app.run(debug=True)
        
