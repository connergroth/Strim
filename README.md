
<img src="https://github.com/user-attachments/assets/9597570b-dd86-4bfa-a957-29f0515cdb14" alt="Strim Logo" width="130"/>

# Strim
  
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

# Tech Stack 
## 🌐 Frontend 
- **HTML, CSS, JavaScript** - UI Components

## 🔧 How It Works
1. Connect your Strava account
2. Select the activity you want to trim
3. Adjust the distance and trim time
4. Strim automatically updates your Strava activity

## 🖥️ Backend 
- **Python** – Core backend language
- **Flask** – Lightweight web framework
- **Flask-Session** – Manages user sessions
- **Gunicorn** – WSGI server for production
- **Requests** – API communication with Strava

## 📡 API Integrations
- **Strava API** – Fetches user activities, deletes untrimmed activity, and reuploads the trimmed one.

