
![Strava Trimmer Logo](https://github.com/user-attachments/assets/9597570b-dd86-4bfa-a957-29f0515cdb14)
# Strim
Ever forgotten to end your Strava run and messed up your pace? Does the treadmill have a different distance than Strava? 

Strim is a tool that allows you to trim your run to the point you stopped running automatically. 
Using the Strava API, Strim automatically fetches your recent activities and allows you to select and edit them. 
It will adjust the distance as specified and adjust your pace accordingly. 

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
- **Backend:** Railway (`https://your-backend-url.railway.app`)
