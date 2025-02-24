
![Strava Trimmer Logo](https://github.com/user-attachments/assets/9597570b-dd86-4bfa-a957-29f0515cdb14)
# Strim
Ever forgotten to end your Strava run? Does the treadmill record a different distance than Strava? 

If you've ever recorded an indoor/treadmill run using the Strava app, you probably found that the recorded distance was way off. 

This is because the app uses the pedometer in your watch/phone to calculate the distance, which is often inaccurate. 

Strim is a tool that allows you to trim your run to the point you stopped running automatically. It also allows you to enter the real distance you ran, correcting any inconsistencies and giving you accurate data.
- Using the Strava API, Strim automatically fetches your recent activities and allows you to select and edit them. 
- It adjusts the distance as specified and adjusts your pace accordingly.
- Strim automatically deletes your existing activity and reuploads the trimmed one.

# Tech Stack 

Strim is built using the following technologies:

## 🌐 Frontend 
- **HTML, CSS, JavaScript** - UI Components

## 🖥️ Backend 
- **Python** – Core backend language
- **Flask** – Lightweight web framework
- **Flask-Session** – Manages user sessions
- **Gunicorn** – WSGI server for production
- **Requests** – API communication with Strava

## 📡 API Integrations
- **Strava API** – Fetches user activities

## 🚀 Deployment
- **Frontend:** Vercel (`strim-madtakvub-conner-groths-projects.vercel.app`)
- **Backend:** Railway (`Deployment in progress`)
