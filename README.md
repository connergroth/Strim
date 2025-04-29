<p align="center">
  <img src="https://github.com/user-attachments/assets/e3c51e88-e84c-426d-8906-c48b2d37a84d" alt="Strim" width="350"/>
</p>

# Strim 
Automatically trim and optimize your Strava running activities with Strim, the tool that transforms inaccurate tracking into precise performance data. Whether you're a treadmill runner or forget to stop your tracker, Strim ensures your running metrics are clean, accurate, and reflective of your true effort.

## 🏃 The Problem
Have you ever forgotten to end your Strava run? Does the treadmill record a different distance than Strava? 

If you've ever recorded an indoor/treadmill run using the Strava app, you probably found that the recorded distance was way off.  This is because the app uses the pedometer in your watch/phone to calculate the distance, which is often inaccurate. 

## 💡 Solution
Strim is a tool that allows you to:
- Trim your run to the point you stopped running automatically
- Enter the real distance you ran
- Correct any inconsistencies
- Ensure accurate running data

## 🚀 Key Features
- Automatically fetches recent Strava activities
- Selectively edit and trim activities
- Adjust distance with precision
- Recalculate pace automatically
- Seamless activity replacement on Strava

## 📊 Data Visualization

- **Interactive Trimming**: Visualize exactly where your activity will be trimmed with draggable markers
- **Automatic Graph Reloading**: Activity visualization graph updates instantly when selecting a new activity

---

# Tech Stack 
## 🌐 Frontend 
- **HTML, CSS, JavaScript** - UI Components

## 🖥️ Backend 
- **Python** – Core backend language
- **Flask** – Lightweight web framework
- **Flask-Session** – Manages user sessions
- **Gunicorn** – WSGI server for production
- **Requests** – API communication with Strava
  
## 📡 API Integrations
- **Strava API** – Fetches user activities, edits relevant metadata, and uploads the new trimmed activity.

## 🔧 How It Works
1. Connect your Strava account
2. Select the activity you want to trim
3. Adjust the distance and trim time
4. Strim automatically updates your Strava activity

---

# Local Development Setup  
Prerequisites:  
- Python 3.8+  
- pip  
- Virtual environment (recommended)  

## ⚙️ Installation Steps  

1. Clone the repository
```
git clone https://github.com/your-username/strim.git  
cd strim  
```
2. Create a virtual environment  
```
python3 -m venv venv  
source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
```
3. Install dependencies
```
pip install -r requirements.txt
```
4. Set up Strava API Credentials
- Create a .env file in the project root
- Add your Strava API credentials:
```
STRAVA_CLIENT_ID=your_client_id  
STRAVA_CLIENT_SECRET=your_client_secret  
STRAVA_REDIRECT_URI=http://localhost:5000/exchange_token
```
5. Run the application
```
flask run
```
