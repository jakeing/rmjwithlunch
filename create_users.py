from app import app, db, User

# Push an application context so that Flask knows which app to use.
with app.app_context():
    # Create all tables (if they don't exist already)
    db.create_all()
    
    # Create a new user (for example, an admin user)
    admin = User(username="admin")
    admin.set_password("adminpassword")

    user1 = User(username="CHinkle")
    user1.set_password("RMJWO2025")

    user2 = User(username="RHinkle")
    user2.set_password("RMJWO2025")

    user3 = User(username="ASeymour")
    user3.set_password("RMJWO2025")
    
    # Add the user to the session and commit to the database
    db.session.add(admin)
    db.session.add(user1)
    db.session.add(user2)
    db.session.add(user3)
    db.session.commit()
    
    print("Admin user created successfully.")
