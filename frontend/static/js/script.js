import config from './config.js';

document.addEventListener("DOMContentLoaded", function() {
  // DOM Elements
  const stravaAuthLink = document.getElementById("stravaAuthLink");
  const authSection = document.getElementById("authSection");
  const activitySection = document.getElementById("activitySection");
  const activityList = document.getElementById("activityList");
  const logoutButton = document.getElementById("logoutButton");
  const trimActivityButton = document.getElementById("trimActivityButton");
  const editDistanceCheckbox = document.getElementById("editDistanceCheckbox");
  const distanceInputContainer = document.getElementById("distanceInputContainer");
  const messageContainer = document.getElementById("message");

  // URLs
  const backendURL = config.getBackendURL();
  
  // Parse URL parameters to check for tokens passed from backend
  const urlParams = new URLSearchParams(window.location.search);
  const authSuccess = urlParams.get("auth_success");
  const authError = urlParams.get("auth_error");
  const tokenFromUrl = urlParams.get("token");
  
  // If we have a token in the URL, store it in localStorage
  if (authSuccess && tokenFromUrl) {
    localStorage.setItem("strava_token", tokenFromUrl);
    
    // Clean the URL to remove the token
    const cleanUrl = window.location.protocol + "//" + window.location.host + window.location.pathname;
    window.history.replaceState({}, document.title, cleanUrl);
    
    showMessage("Successfully connected to Strava!", "success");
  }
  
  // Check for auth errors
  if (authError) {
    showMessage(`Authentication error: ${authError}`, "error");
  }

  // Initialize Strava Auth Link
  if (stravaAuthLink) {
    stravaAuthLink.addEventListener("click", function(e) {
      e.preventDefault();
      window.location.href = `${backendURL}/auth`;
    });
  }

  // Toggle distance input visibility
  if (editDistanceCheckbox) {
    editDistanceCheckbox.addEventListener("change", function() {
      distanceInputContainer.style.display = this.checked ? "block" : "none";
    });
  }

  // Logout functionality
  if (logoutButton) {
    logoutButton.addEventListener("click", function() {
      localStorage.removeItem("strava_token");
      authSection.classList.remove("hidden");
      activitySection.classList.add("hidden");
      
      // Optional: Also notify the backend to clear the server-side session
      fetch(`${backendURL}/logout`, {
        method: "POST",
        credentials: "include"
      })
      .then(response => response.json())
      .then(data => {
        console.log("Logged out successfully");
      })
      .catch(error => {
        console.error("Error logging out:", error);
      });
    });
  }

  // Check if user has a token in localStorage
  const token = localStorage.getItem("strava_token");
  
  if (token) {
    // User has a token, check if it's valid by fetching activities
    fetchActivities(token);
  } else {
    // No token, show auth section
    authSection.classList.remove("hidden");
    activitySection.classList.add("hidden");
  }

  // Handle activity trimming
  if (trimActivityButton) {
    trimActivityButton.addEventListener("click", trimSelectedActivity);
  }

  // Functions
  function fetchActivities(token) {
    // Show loading indicator
    activityList.innerHTML = '<tr><td colspan="4">Loading activities...</td></tr>';
    
    fetch(`${backendURL}/activities?token=${token}`, {
      headers: {
        "Authorization": `Bearer ${token}`
      }
    })
    .then(response => {
      if (!response.ok) {
        throw new Error(`HTTP error! Status: ${response.status}`);
      }
      return response.json();
    })
    .then(data => {
      // Update the token if the server sent an updated one
      if (data.token) {
        localStorage.setItem("strava_token", data.token);
      }
      
      if (data.activities && data.activities.length > 0) {
        displayActivities(data.activities);
        authSection.classList.add("hidden");
        activitySection.classList.remove("hidden");
      } else {
        activityList.innerHTML = '<tr><td colspan="4">No running activities found.</td></tr>';
        authSection.classList.add("hidden");
        activitySection.classList.remove("hidden");
      }
    })
    .catch(error => {
      console.error("Error fetching activities:", error);
      activityList.innerHTML = '<tr><td colspan="4">Error loading activities. Please try again.</td></tr>';
      
      // If we get an error, it might be because the token is invalid
      // Clear the token and show auth section
      if (error.message.includes("401")) {
        localStorage.removeItem("strava_token");
        authSection.classList.remove("hidden");
        activitySection.classList.add("hidden");
        showMessage("Your session has expired. Please log in again.", "error");
      }
    });
  }

  function displayActivities(activities) {
    activityList.innerHTML = '';
    
    activities.forEach(activity => {
      const row = document.createElement('tr');
      
      row.innerHTML = `
        <td>${activity.name}</td>
        <td>${activity.distance_miles}</td>
        <td>${formatDate(new Date(activity.date))}</td>
        <td>
          <input type="radio" name="selectedActivity" value="${activity.id}" data-distance="${activity.distance_miles}">
        </td>
      `;
      
      activityList.appendChild(row);
    });
  }

  function formatDate(date) {
    return date.toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric'
    });
  }

  function trimSelectedActivity() {
    const selectedActivity = document.querySelector('input[name="selectedActivity"]:checked');
    
    if (!selectedActivity) {
      showMessage("Please select an activity to trim", "error");
      return;
    }
    
    const activityId = selectedActivity.value;
    const editDistance = editDistanceCheckbox.checked;
    let newDistance = null;
    
    if (editDistance) {
      newDistance = document.getElementById("newDistance").value;
      
      if (!newDistance || isNaN(newDistance) || parseFloat(newDistance) <= 0) {
        showMessage("Please enter a valid distance", "error");
        return;
      }
    }
    
    // Disable the button and show loading message
    trimActivityButton.disabled = true;
    trimActivityButton.textContent = "Processing...";
    showMessage("Processing your activity. This may take a moment...", "info");
    
    const token = localStorage.getItem("strava_token");
    let url = `${backendURL}/download-fit?activity_id=${activityId}&edit_distance=${editDistance}`;
    
    if (editDistance && newDistance) {
      url += `&new_distance=${newDistance}`;
    }
    
    // Add token to URL
    url += `&token=${token}`;
    
    fetch(url, {
      headers: {
        "Authorization": `Bearer ${token}`
      }
    })
    .then(response => {
      if (!response.ok) {
        return response.json().then(data => {
          throw new Error(data.error || `Server error: ${response.status}`);
        });
      }
      return response.json();
    })
    .then(data => {
      if (data.success) {
        trimActivityButton.disabled = false;
        trimActivityButton.textContent = "Trim Activity";
        showMessage("Activity processed successfully! Refresh your Strava to see the updated activity.", "success");
        
        // Refresh the activities list
        setTimeout(() => {
          fetchActivities(token);
        }, 2000);
      } else {
        throw new Error(data.error || "Unknown error occurred");
      }
    })
    .catch(error => {
      console.error("Error trimming activity:", error);
      trimActivityButton.disabled = false;
      trimActivityButton.textContent = "Trim Activity";
      showMessage(`Error: ${error.message}`, "error");
    });
  }

  function showMessage(message, type) {
    messageContainer.textContent = message;
    messageContainer.className = `message ${type}`;
    messageContainer.style.display = "block";
    
    // Hide the message after 5 seconds
    setTimeout(() => {
      messageContainer.style.display = "none";
    }, 5000);
  }
});