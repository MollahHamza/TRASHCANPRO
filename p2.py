import streamlit as st
import folium
from streamlit_folium import st_folium
import pandas as pd
import random
import os
import hashlib
import json
import traceback
from PIL import Image
from exif import Image as ExifImage

class UserManager:
    def __init__(self):
        self.users_file = 'users.json'
        self.users = self.load_users()
        self.current_user = None

    def load_users(self):
        if os.path.exists(self.users_file):
            with open(self.users_file, 'r') as f:
                return json.load(f)
        return {
            'admin': {
                'password': self._hash_password('1234'),
                'role': 'admin',
                'points': 0
            },
            'user': {
                'password': self._hash_password('user'),
                'role': 'standard',
                'points': 0
            }
        }

    def save_users(self):
        with open(self.users_file, 'w') as f:
            json.dump(self.users, f, indent=4)

    def _hash_password(self, password):
        return hashlib.sha256(password.encode()).hexdigest()

    def login(self, username, password):
        hashed_password = self._hash_password(password)
        if (username in self.users and 
            self.users[username]['password'] == hashed_password):
            self.current_user = {
                'username': username,
                'role': self.users[username].get('role', 'standard')
            }
            return True
        return False

    def add_points(self, username, points):
        if username in self.users:
            self.users[username]['points'] += points
            self.save_users()

    def get_points(self, username):
        return self.users.get(username, {}).get('points', 0)

    def deduct_points(self, username, points):
        if username in self.users:
            self.users[username]['points'] = max(
                0, 
                self.users[username]['points'] - points
            )
            self.save_users()

    def logout(self):
        self.current_user = None

class WasteReportDatabase:
    def __init__(self, user_manager):
        self.waste_reports_file = 'waste_reports.json'
        self.uploads_dir = "waste_report_images"
        os.makedirs(self.uploads_dir, exist_ok=True)
        self.user_manager = user_manager
        self.waste_reports = self.load_waste_reports()

    def load_waste_reports(self):
        if os.path.exists(self.waste_reports_file):
            with open(self.waste_reports_file, 'r') as f:
                return json.load(f)
        return []

    def save_waste_reports(self):
        with open(self.waste_reports_file, 'w') as f:
            json.dump(self.waste_reports, f, indent=4)

    def extract_gps(self, image_path):
        try:
            with open(image_path, 'rb') as img_file:
                img = ExifImage(img_file)
                if img.has_exif and 'gps_latitude' in img.list_all():
                    lat = img.gps_latitude
                    lon = img.gps_longitude

                    lat_decimal = lat[0] + lat[1] / 60 + lat[2] / 3600
                    if img.gps_latitude_ref == 'S':
                        lat_decimal *= -1

                    lon_decimal = lon[0] + lon[1] / 60 + lon[2] / 3600
                    if img.gps_longitude_ref == 'W':
                        lon_decimal *= -1

                    return lat_decimal, lon_decimal
                return None, None
        except Exception:
            return None, None

    def add_waste_report(self, user, report_type, image):
        try:
            # Generate unique filename
            filename = f"{user}_{len(self.waste_reports) + 1}_{image.name}"
            filepath = os.path.join(self.uploads_dir, filename)
            
            # Save image
            with open(filepath, "wb") as f:
                f.write(image.getbuffer())

            # Try to extract GPS, use random if fails
            lat, lon = self.extract_gps(filepath)
            location = {
                'latitude': lat or random.uniform(40.7, 40.8),
                'longitude': lon or random.uniform(-74.1, -73.9)
            }

            # Create report
            report = {
                "id": len(self.waste_reports) + 1,
                "user": user,
                "location": location,
                "type": report_type,
                "timestamp": str(pd.Timestamp.now()),
                "status": "Pending Review",
                "image_path": filepath
            }
            self.waste_reports.append(report)
            self.save_waste_reports()
            
            # Add points 
            self.user_manager.add_points(user, 50)
            
            return report
        except Exception as e:
            print(f"Error in add_waste_report: {e}")
            print(traceback.format_exc())
            return None

def login_page(user_manager):
    st.title("GreenCycle Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    
    if st.button("Login"):
        if user_manager.login(username, password):
            st.session_state['logged_in'] = True
            st.session_state['username'] = username
            st.session_state['user_role'] = user_manager.current_user['role']
            st.rerun()
        else:
            st.error("Invalid credentials")

def main_app(user_manager, waste_db):
    st.set_page_config(page_title="GreenCycle", page_icon=":recycle:")
    
    if st.sidebar.button("Logout"):
        user_manager.logout()
        st.session_state['logged_in'] = False
        st.rerun()

    st.sidebar.write(f"Welcome, {st.session_state['username']}")
    st.sidebar.write(f"Points: {user_manager.get_points(st.session_state['username'])}")
    
    menu = st.sidebar.radio("Navigate", 
        ["Home", "Waste Reporting", "Recycling Map", "Points & Rewards", "Community Challenges"])

    if menu == "Home":
        home_page(user_manager, waste_db)
    elif menu == "Waste Reporting":
        waste_reporting_page(waste_db)
    elif menu == "Recycling Map":
        recycling_map_page(waste_db)
    elif menu == "Points & Rewards":
        points_rewards_page(user_manager)
    elif menu == "Community Challenges":
        community_challenges_page()

def home_page(user_manager, waste_db):
    st.title("Welcome to GreenCycle")
    st.metric("Total Community Points", sum(user.get('points', 0) for user in user_manager.users.values()))
    st.metric("Total Waste Reports", len(waste_db.waste_reports))

def waste_reporting_page(waste_db):
    st.header("Waste Reporting")
    
    report_type = st.selectbox("Report Type", [
        "Overflowing Bin", 
        "Illegal Dumping", 
        "Recyclables in Wrong Bin"
    ])
    
    uploaded_file = st.file_uploader("Upload Image", type=['png', 'jpg', 'jpeg'])
    
    # Reset submit_clicked if file changes to prevent stale state
    if 'last_uploaded_file' not in st.session_state or st.session_state.last_uploaded_file != uploaded_file:
        st.session_state.last_uploaded_file = uploaded_file
        st.session_state.submit_clicked = False

    # Submission button 
    if st.button("Submit Report"):
        st.session_state.submit_clicked = True

    # Check if submission was attempted
    if hasattr(st.session_state, 'submit_clicked') and st.session_state.submit_clicked:
        if uploaded_file is not None:
            try:
                report = waste_db.add_waste_report(
                    st.session_state['username'], 
                    report_type, 
                    uploaded_file
                )
                if report:
                    st.success(f"Report submitted! 50 points added to your account.")
                    # Reset submission state
                    st.session_state.submit_clicked = False
                else:
                    st.error("Failed to submit report")
            except Exception as e:
                st.error(f"Unexpected error: {e}")
                print(traceback.format_exc())
        else:
            st.warning("Please upload an image before submitting")
            # Reset submission state
            st.session_state.submit_clicked = False

def recycling_map_page(waste_db):
    st.header("Community Waste Reports Map")
    
    m = folium.Map(location=[40.7128, -74.0060], zoom_start=10)
    
    for report in waste_db.waste_reports:
        # Distinct icons for different waste report types
        icon_colors = {
            "Overflowing Bin": "green",
            "Illegal Dumping": "red", 
            "Recyclables in Wrong Bin": "orange"
        }
        color = icon_colors.get(report['type'], 'blue')
        
        popup_content = f"""
        <b>Type:</b> {report['type']}<br>
        <b>Reported by:</b> {report['user']}<br>
        <b>Time:</b> {report['timestamp']}<br>
        <img src="{report['image_path']}" width="200">
        """
        folium.Marker(
            [report['location']['latitude'], report['location']['longitude']], 
            popup=folium.Popup(popup_content, max_width=300),
            icon=folium.Icon(color=color, icon='info-sign')
        ).add_to(m)
    
    st_folium(m, width=700, height=500)

def points_rewards_page(user_manager):
    st.header("Points & Rewards")
    
    points = user_manager.get_points(st.session_state['username'])
    st.write(f"Your Points: {points}")
    
    reward_options = {
        "Tree Planting Certificate": 500,
        "Reusable Water Bottle": 250,
        "Compost Bin": 750
    }
    
    for reward, cost in reward_options.items():
        col1, col2 = st.columns([3, 1])
        with col1:
            st.write(f"{reward} (Cost: {cost} points)")
        with col2:
            if st.button(f"Redeem {reward}"):
                if points >= cost:
                    user_manager.deduct_points(st.session_state['username'], cost)
                    st.success(f"Redeemed {reward}!")
                    st.rerun()
                else:
                    st.warning("Not enough points")

def community_challenges_page():
    st.header("Community Challenges")
    
    challenges = [
        {
            "name": "Neighborhood Cleanup",
            "description": "Collect most waste in neighborhood",
            "points": 200
        },
        {
            "name": "Recycling Champion",
            "description": "Report recyclables correctly",
            "points": 150
        }
    ]
    
    for challenge in challenges:
        st.subheader(challenge['name'])
        st.write(challenge['description'])
        if st.button(f"Join {challenge['name']}"):
            st.success("Challenge joined!")

def main():
    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False
    
    # Initialize user manager and waste database
    user_manager = UserManager()
    waste_db = WasteReportDatabase(user_manager)
    
    if not st.session_state['logged_in']:
        login_page(user_manager)
    else:
        main_app(user_manager, waste_db)

if __name__ == "__main__":
    main()