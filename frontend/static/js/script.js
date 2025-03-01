// Update the BACKEND_URL to be environment-aware
const BACKEND_URL = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1"
  ? "http://localhost:8080"  // Local development backend URL
  : "https://strim-production.up.railway.app";  // Production backend URL

/**
 * Check if user is authenticated and redirect if needed
 */
function checkAuthStatus() {
    console.log("Checking authentication status...");
    
    // Use config.js to get the backend URL
    const BACKEND_URL = config.getBackendURL();
    console.log(`Using backend URL: ${BACKEND_URL}`);
    
    fetch(`${BACKEND_URL}/api/session-status`, {
        method: "GET",
        credentials: "include",  // Crucial for sending cookies with request
        headers: {
            // Add a cache-busting parameter to avoid cached responses
            'Cache-Control': 'no-cache, no-store, must-revalidate'
        }
    })
    .then(response => {
        console.log(`Auth status response code: ${response.status}`);
        if (!response.ok) {
            throw new Error(`Server returned ${response.status}: ${response.statusText}`);
        }
        return response.json();
    })
    .then(data => {
        console.log("Auth status response data:", data);
        if (data.authenticated) {
            console.log("✅ User is authenticated");
            
            // If we're on the main page, show the activity section
            if (window.location.pathname === "/" || 
                window.location.pathname === "/index.html") {
                document.getElementById("authSection").classList.add("hidden");
                document.getElementById("activitySection").classList.remove("hidden");
                fetchActivities();
            }
            
            // Add visual indicator that user is logged in
            document.querySelector('.footer').insertAdjacentHTML(
                'beforeend', 
                `<div class="auth-status">Logged in as: ${data.athlete?.firstname || 'Athlete'}</div>`
            );
        } else {
            console.log(`❌ User is NOT authenticated: ${data.reason || 'Unknown reason'}`);
            
            // If not on index page, redirect to login
            if (window.location.pathname !== "/index.html" && 
                window.location.pathname !== "/") {
                window.location.href = "/index.html";
            }
            
            // Ensure auth section is visible on index page
            if (document.getElementById("authSection")) {
                document.getElementById("authSection").classList.remove("hidden");
            }
            if (document.getElementById("activitySection")) {
                document.getElementById("activitySection").classList.add("hidden");
            }
        }
    })
    .catch(error => {
        console.error("Error checking auth status:", error);
        
        // Show error message to user
        const errorMsg = document.createElement('div');
        errorMsg.className = 'error-message';
        errorMsg.textContent = `Authentication error: ${error.message}. Please try refreshing the page.`;
        document.body.prepend(errorMsg);
    });
}

/**
 * Fetch user's activities from Strava
 */
async function fetchActivities() {
    try {
        console.log("Fetching activities...");
        const BACKEND_URL = config.getBackendURL();

        // Show loading indicator
        document.getElementById("activityList").innerHTML = "<tr><td colspan='4'>Loading activities...</td></tr>";

        const response = await fetch(`${BACKEND_URL}/activities`, {
            method: "GET",
            credentials: "include",  // Ensures cookies are sent
            headers: {
                "Content-Type": "application/json",
                'Cache-Control': 'no-cache, no-store, must-revalidate'
            }
        });

        if (!response.ok) {
            console.error(`❌ Error fetching activities: ${response.status} ${response.statusText}`);

            if (response.status === 401) {
                console.log("Session expired, showing login prompt");
                alert("Session expired. Please log in again.");
                window.location.href = "/index.html";  // Redirect to login
            } else {
                document.getElementById("activityList").innerHTML = 
                    `<tr><td colspan='4'>Error loading activities: ${response.status} ${response.statusText}</td></tr>`;
            }
            return;
        }

        const data = await response.json();
        console.log("✅ Fetched activities:", data);

        if (!data.activities || data.activities.length === 0) {
            document.getElementById("activityList").innerHTML = 
                "<tr><td colspan='4'>No activities found. Make sure you have activities on Strava.</td></tr>";
            return;
        }

        const activityList = document.getElementById("activityList");
        activityList.innerHTML = "";

        data.activities.forEach(activity => {
            let row = document.createElement("tr");
            row.innerHTML = `
                <td>${activity.name}</td>
                <td>${activity.distance_miles.toFixed(2)}</td>
                <td>${new Date(activity.date).toLocaleDateString()}</td>
                <td><input type="radio" name="selectedActivity" value="${activity.id}"></td>
            `;
            activityList.appendChild(row);
        });

    } catch (error) {
        console.error("❌ Network error fetching activities:", error);
        document.getElementById("activityList").innerHTML = 
            `<tr><td colspan='4'>Failed to load activities: ${error.message}</td></tr>`;
        alert("Failed to load activities. Please try again.");
    }
}

/**
 * Toggle distance input visibility based on checkbox
 */
function toggleDistanceInput() {
    const editDistanceChecked = document.getElementById("editDistanceCheckbox").checked;
    document.getElementById("distanceInputContainer").style.display = editDistanceChecked ? "block" : "none";
}

/**
 * Process selected activity and send to backend
 */
async function downloadAndProcessActivity() {
    const selectedActivity = document.querySelector('input[name="selectedActivity"]:checked');
    if (!selectedActivity) {
        alert("Please select an activity.");
        return;
    }

    const activityId = selectedActivity.value;
    const editDistance = document.getElementById("editDistanceCheckbox").checked;
    let newDistance = editDistance ? document.getElementById("newDistance").value : null;

    if (editDistance && (!newDistance || parseFloat(newDistance) <= 0)) {
        alert("Please enter a valid new distance.");
        return;
    }

    try {
        document.getElementById("message").innerText = "Downloading and processing activity...";

        // Ensure newDistance is properly encoded
        const encodedDistance = newDistance ? encodeURIComponent(newDistance) : "";
        const url = `${BACKEND_URL}/download-fit?activity_id=${activityId}&edit_distance=${editDistance}&new_distance=${encodedDistance}`;

        const response = await fetch(url, {
            method: "GET",
            credentials: "include"  // Ensure cookies are sent
        });
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || "Failed to process activity");
        }

        const result = await response.json();

        if (result.success) {
            document.getElementById("message").innerText = "Upload complete! Redirecting to Strava...";
            window.location.href = `https://www.strava.com/activities/${result.new_activity_id}`;
        } else {
            alert("Error: " + result.error);
        }
    } catch (error) {
        console.error("Error processing activity:", error);
        document.getElementById("message").innerText = "";
        alert("An error occurred while processing the activity: " + error.message);
    }
}

/**
 * Handle logout
 */
function logout() {
    console.log("🔴 Logging out...");
    
    fetch(`${BACKEND_URL}/logout`, {
        method: "POST",
        credentials: "include" // Send cookies
    })
    .then(() => {
        // Redirect to login page
        window.location.href = "/index.html";
    })
    .catch(error => {
        console.error("Error logging out:", error);
        window.location.href = "/index.html";
    });
}

/**
 * Initialize on page load
 */
document.addEventListener("DOMContentLoaded", function () {
    console.log("Document loaded, checking authentication...");
    
    // Configure Strava auth link
    const stravaAuthLink = document.getElementById("stravaAuthLink");
    if (stravaAuthLink) {
        stravaAuthLink.href = `${BACKEND_URL}/auth`;
    }
    
    // Check if redirected from OAuth
    const urlParams = new URLSearchParams(window.location.search);
    const code = urlParams.get("code");
    
    if (code) {
        console.log("🔑 OAuth Code Found:", code);
        // Remove code from URL to prevent issues on refresh
        window.history.replaceState({}, document.title, window.location.pathname);
    }
    
    // Check auth status and load appropriate view
    checkAuthStatus();
});