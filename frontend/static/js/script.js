// Production-only script with hardcoded URLs
const BACKEND_URL = "https://strim-production.up.railway.app";
const FRONTEND_URL = "https://strimrun.vercel.app";

/**
 * Show a message to the user with improved handling of empty messages
 */
function showMessage(text, type = "info") {
    const message = document.getElementById("message");
    if (!message) return;
    
    if (!text || text.trim() === "") {
        // If no message, completely hide the element
        message.textContent = "";
        message.style.display = "none";
        message.className = "";
        return;
    }
    
    // Otherwise show the message properly
    message.textContent = text;
    message.style.display = "block";
    message.className = type || "info";
}

// Make sure to initialize the message as hidden
document.addEventListener("DOMContentLoaded", function() {
    const message = document.getElementById("message");
    if (message) {
        message.style.display = "none";
        message.textContent = "";
    }
    
    // Rest of your initialization code...
});

/**
 * Check if user is authenticated and redirect if needed
 */
function checkAuthStatus() {
    console.log("Checking authentication status...");
    
    // First, check for auth success/error URL parameters (from redirect)
    const urlParams = new URLSearchParams(window.location.search);
    const authSuccess = urlParams.get("auth_success");
    const authError = urlParams.get("auth_error");
    const errorMsg = urlParams.get("message");
    const token = urlParams.get("token"); // NEW: Get token from URL params
    
    // If token is in URL, store it in localStorage
    if (token) {
        console.log("✅ Token found in URL, storing in localStorage");
        localStorage.setItem('strava_token', token);
    }
    
    // Remove query parameters from URL to prevent issues on refresh
    if (authSuccess || authError || token) {
        window.history.replaceState({}, document.title, window.location.pathname);
    }
    
    // Handle auth error from redirect
    if (authError) {
        console.error(`❌ Authentication error: ${authError}`);
        if (errorMsg) {
            console.error(`Error details: ${errorMsg}`);
        }
        
        // Display error message to user
        showMessage(`Authentication failed: ${authError}. Please try again.`, "error");
        
        // Ensure auth section is visible on index page
        document.getElementById("authSection").classList.remove("hidden");
        document.getElementById("activitySection").classList.add("hidden");
        return;
    }
    
    // If auth_success=true is in URL, we just completed authentication
    if (authSuccess === "true") {
        console.log("✅ Authentication successful from redirect");
        
        // Show a success message briefly
        showMessage("Successfully authenticated with Strava!", "success");
        setTimeout(() => {
            showMessage("");
        }, 3000);
        
        // Show activity section and fetch activities
        document.getElementById("authSection").classList.add("hidden");
        document.getElementById("activitySection").classList.remove("hidden");
        fetchActivities();
        return;
    }
    
    // Check if we have a token in localStorage
    const storedToken = localStorage.getItem('strava_token');
    if (storedToken) {
        console.log("✅ Found token in localStorage, using it");
        document.getElementById("authSection").classList.add("hidden");
        document.getElementById("activitySection").classList.remove("hidden");
        fetchActivities();
        return;
    }
    
    // If no token in localStorage, check session status from backend
    console.log("No stored token, checking session status quietly...");
    
    fetch(`${BACKEND_URL}/api/session-status`, {
        method: "GET",
        credentials: "include"  // Send cookies with request
    })
    .then(response => {
        if (!response.ok) {
            console.log(`Auth check returned ${response.status} - not authenticated`);
            document.getElementById("authSection").classList.remove("hidden");
            document.getElementById("activitySection").classList.add("hidden");
            return null;
        }
        return response.json();
    })
    .then(data => {
        if (!data) return; // Skip if response wasn't ok
        
        console.log("Auth status response:", data);
        if (data.authenticated) {
            console.log("✅ User is authenticated");
            
            // NEW: Store token in localStorage if provided
            if (data.token) {
                console.log("✅ Storing token from session in localStorage");
                localStorage.setItem('strava_token', data.token);
            }
            
            // Show the activity section
            document.getElementById("authSection").classList.add("hidden");
            document.getElementById("activitySection").classList.remove("hidden");
            fetchActivities();
        } else {
            console.log(`❌ User is NOT authenticated: ${data.reason || 'unknown reason'}`);
            
            document.getElementById("authSection").classList.remove("hidden");
            document.getElementById("activitySection").classList.add("hidden");
        }
    })
    .catch(error => {
        console.error("Error checking auth status:", error);
        
        document.getElementById("authSection").classList.remove("hidden");
        document.getElementById("activitySection").classList.add("hidden");
    });
}

/**
 * Fetch user's activities from Strava with improved error handling and token usage
 */
async function fetchActivities() {
    try {
        console.log("Fetching activities...");

        // Show loading indicator
        document.getElementById("activityList").innerHTML = "<tr><td colspan='4'>Loading activities...</td></tr>";

        // Get token from localStorage
        const token = localStorage.getItem('strava_token');
        
        // Create URL with token parameter
        const url = token 
            ? `${BACKEND_URL}/activities?token=${encodeURIComponent(token)}` 
            : `${BACKEND_URL}/activities`;
            
        console.log(`📡 Making request to: ${token ? `${BACKEND_URL}/activities?token=***MASKED***` : url}`);

        // Make request with token in URL and also in credentials
        const response = await fetch(url, {
            method: "GET",
            credentials: "include",  // Ensures cookies are sent
            headers: token ? { 'Authorization': `Bearer ${token}` } : {}
        });

        if (!response.ok) {
            console.error(`❌ Error fetching activities: ${response.status} ${response.statusText}`);

            if (response.status === 401) {
                console.log("Session expired, showing login prompt");
                localStorage.removeItem('strava_token'); // Clear invalid token
                showMessage("Session expired. Please log in again.", "error");
                
                // Wait a moment before redirecting
                setTimeout(() => {
                    document.getElementById("authSection").classList.remove("hidden");
                    document.getElementById("activitySection").classList.add("hidden");
                }, 2000);
            } else {
                document.getElementById("activityList").innerHTML = 
                    `<tr><td colspan='4'>Error loading activities: ${response.status} ${response.statusText}</td></tr>`;
            }
            return;
        }

        const data = await response.json();
        console.log("✅ Fetched activities:", data);

        // NEW: If token is in the response, store it
        if (data.token) {
            console.log("✅ Updating token from activities response");
            localStorage.setItem('strava_token', data.token);
        }

        if (!data.activities || data.activities.length === 0) {
            document.getElementById("activityList").innerHTML = 
                "<tr><td colspan='4'>No activities found. Make sure you have running activities on Strava.</td></tr>";
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
        
        if (error.message.includes("NetworkError") || error.message.includes("Failed to fetch")) {
            document.getElementById("activityList").innerHTML = 
                `<tr><td colspan='4'>Connection error: Unable to reach the server. If this persists, please try again later.</td></tr>`;
            
            showMessage("Connection error: Unable to reach the server. This may be a temporary issue.", "error");
        } else {
            document.getElementById("activityList").innerHTML = 
                `<tr><td colspan='4'>Failed to load activities: ${error.message}</td></tr>`;
        }
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
 * Process selected activity and send to backend - now with token support
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
        showMessage("Downloading and processing activity...", "info");

        // Get token from localStorage
        const token = localStorage.getItem('strava_token');
        
        // Ensure newDistance is properly encoded
        const encodedDistance = newDistance ? encodeURIComponent(newDistance) : "";
        
        // Include token in the URL if available
        let url = `${BACKEND_URL}/download-fit?activity_id=${activityId}&edit_distance=${editDistance}&new_distance=${encodedDistance}`;
        if (token) {
            url += `&token=${encodeURIComponent(token)}`;
        }

        const response = await fetch(url, {
            method: "GET",
            credentials: "include",  // Send cookies 
            headers: token ? { 'Authorization': `Bearer ${token}` } : {}
        });
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || "Failed to process activity");
        }

        const result = await response.json();

        if (result.success) {
            showMessage("Upload complete! Redirecting to Strava...", "success");
            setTimeout(() => {
                window.location.href = `https://www.strava.com/activities/${result.new_activity_id}`;
            }, 1000);
        } else {
            throw new Error(result.error || "Unknown error occurred");
        }
    } catch (error) {
        console.error("Error processing activity:", error);
        showMessage(`Error: ${error.message}`, "error");
    }
}

/**
 * Handle logout - now clears local storage too
 */
function logout() {
    console.log("🔴 Logging out...");
    showMessage("Logging out...", "info");
    
    // Clear the token from localStorage
    localStorage.removeItem('strava_token');
    
    fetch(`${BACKEND_URL}/logout`, {
        method: "POST",
        credentials: "include" // Send cookies
    })
    .then(() => {
        showMessage("Logged out successfully", "success");
        setTimeout(() => {
            // Show login page
            document.getElementById("authSection").classList.remove("hidden");
            document.getElementById("activitySection").classList.add("hidden");
        }, 1000);
    })
    .catch(error => {
        console.error("Error logging out:", error);
        showMessage("Error logging out", "error");
        setTimeout(() => {
            document.getElementById("authSection").classList.remove("hidden");
            document.getElementById("activitySection").classList.add("hidden");
        }, 1000);
    });
}

/**
 * Initialize on page load
 */
document.addEventListener("DOMContentLoaded", function () {
    console.log("Document loaded, initializing app...");
    console.log(`Backend URL: ${BACKEND_URL}`);
    
    // Add message styles if not already in CSS
    if (!document.querySelector('style#message-styles')) {
        const style = document.createElement('style');
        style.id = 'message-styles';
        style.textContent = `
            #message {
                padding: 10px;
                margin: 10px 0;
                border-radius: 5px;
                font-weight: 500;
                min-height: 24px;
            }
            #message.error {
                background-color: #ffecec;
                color: #d63301;
                border-left: 4px solid #d63301;
            }
            #message.success {
                background-color: #dff2de;
                color: #257825;
                border-left: 4px solid #257825;
            }
            #message.info {
                background-color: #e0f1ff;
                color: #0055aa;
                border-left: 4px solid #0055aa;
            }
        `;
        document.head.appendChild(style);
    }
    
    // Configure Strava auth link
    const stravaAuthLink = document.getElementById("stravaAuthLink");
    if (stravaAuthLink) {
        stravaAuthLink.href = `${BACKEND_URL}/auth`;
        console.log(`Set auth link to: ${stravaAuthLink.href}`);
    }
    
    // Explicitly set up the event handlers for the buttons
    const toggleCheckbox = document.getElementById("editDistanceCheckbox");
    if (toggleCheckbox) {
        toggleCheckbox.addEventListener("change", toggleDistanceInput);
    }
    
    const trimButton = document.querySelector("#activitySection button");
    if (trimButton) {
        trimButton.addEventListener("click", downloadAndProcessActivity);
    }
    
    const logoutButton = document.getElementById("logoutButton");
    if (logoutButton) {
        logoutButton.addEventListener("click", logout);
    }
    
    // Check auth status and load appropriate view
    checkAuthStatus();
});

// Make sure the functions are exposed to the global scope
window.toggleDistanceInput = toggleDistanceInput;
window.downloadAndProcessActivity = downloadAndProcessActivity;
window.logout = logout;

// Explicitly confirm the functions are attached to the window object
console.log("✅ Global functions attached:", {
    toggleDistanceInput: typeof window.toggleDistanceInput === 'function',
    downloadAndProcessActivity: typeof window.downloadAndProcessActivity === 'function',
    logout: typeof window.logout === 'function'
});