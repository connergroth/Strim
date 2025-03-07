// Production-only script with hardcoded URLs
const BACKEND_URL = "https://strim-production.up.railway.app";
const FRONTEND_URL = "https://strimrun.vercel.app";

/**
 * Show a message to the user
 */
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
    
    // Remove query parameters from URL to prevent issues on refresh
    if (authSuccess || authError) {
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
    
    // If no auth parameters, check session status from backend
    // But don't show any error messages yet - this is just a check
    console.log("No auth parameters, checking session status quietly...");
    
    fetch(`${BACKEND_URL}/api/session-status`, {
        method: "GET",
        credentials: "include"  // Send cookies with request
    })
    .then(response => {
        if (!response.ok) {
            // Don't throw an error here, just handle the failed auth silently
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
            
            // Show the activity section
            document.getElementById("authSection").classList.add("hidden");
            document.getElementById("activitySection").classList.remove("hidden");
            fetchActivities();
        } else {
            console.log(`❌ User is NOT authenticated: ${data.reason || 'unknown reason'}`);
            
            // Silent failure - just show auth section
            document.getElementById("authSection").classList.remove("hidden");
            document.getElementById("activitySection").classList.add("hidden");
        }
    })
    .catch(error => {
        console.error("Error checking auth status:", error);
        
        // Silently fail - don't show error messages on initial page load
        document.getElementById("authSection").classList.remove("hidden");
        document.getElementById("activitySection").classList.add("hidden");
    });
}

/**
 * Fetch user's activities from Strava
 */
async function fetchActivities() {
    try {
        console.log("Fetching activities...");

        // Show loading indicator
        document.getElementById("activityList").innerHTML = "<tr><td colspan='4'>Loading activities...</td></tr>";

        // Add retry logic
        let retries = 0;
        const maxRetries = 2;
        let success = false;
        let response;

        while (!success && retries <= maxRetries) {
            try {
                if (retries > 0) {
                    console.log(`Retry attempt ${retries}/${maxRetries}...`);
                    // Add a small delay between retries
                    await new Promise(resolve => setTimeout(resolve, 1000));
                }

                response = await fetch(`${BACKEND_URL}/activities`, {
                    method: "GET",
                    credentials: "include",  // Ensures cookies are sent
                    headers: {
                        'Cache-Control': 'no-cache',
                        'Pragma': 'no-cache'
                    }
                });
                
                if (response.ok) {
                    success = true;
                } else {
                    retries++;
                    
                    // If we get a 401, try to refresh the session
                    if (response.status === 401 && retries <= maxRetries) {
                        console.log("Session may be expired, checking status...");
                        
                        const statusResp = await fetch(`${BACKEND_URL}/api/session-status`, {
                            method: "GET",
                            credentials: "include",
                            headers: {
                                'Cache-Control': 'no-cache',
                                'Pragma': 'no-cache'
                            }
                        });
                        
                        if (!statusResp.ok || !(await statusResp.json()).authenticated) {
                            throw new Error("Session expired or invalid");
                        }
                    }
                }
            } catch (retryError) {
                retries++;
                console.error(`Fetch retry ${retries} failed:`, retryError);
                
                if (retries > maxRetries) {
                    throw retryError;
                }
            }
        }

        if (!success) {
            console.error(`❌ Error fetching activities after ${maxRetries} retries: ${response.status} ${response.statusText}`);

            if (response.status === 401) {
                console.log("Session expired, showing login prompt");
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
        document.getElementById("activityList").innerHTML = 
            `<tr><td colspan='4'>Failed to load activities: ${error.message}</td></tr>`;
        
        // Add more helpful message for CORS errors
        if (error.message.includes("NetworkError") || error.message.includes("Failed to fetch")) {
            document.getElementById("activityList").innerHTML = 
                `<tr><td colspan='4'>CORS error: The server is not accessible from this domain. Please check server configuration.</td></tr>`;
            
            showMessage("CORS error: Unable to connect to the server. This may be a temporary issue or a server configuration problem.", "error");
        }
        
        // Check if this is a session error and offer relogin
        if (error.message.includes("Session expired") || error.message.includes("401")) {
            showMessage("Your session has expired. Please log in again.", "error");
            setTimeout(() => {
                document.getElementById("authSection").classList.remove("hidden");
                document.getElementById("activitySection").classList.add("hidden");
            }, 2000);
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
        showMessage("Downloading and processing activity...", "info");

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
 * Handle logout
 */
function logout() {
    console.log("🔴 Logging out...");
    showMessage("Logging out...", "info");
    
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
// This is redundant with the event listeners above but provides a fallback
window.toggleDistanceInput = toggleDistanceInput;
window.downloadAndProcessActivity = downloadAndProcessActivity;
window.logout = logout;

// Explicitly confirm the functions are attached to the window object
console.log("✅ Global functions attached:", {
    toggleDistanceInput: typeof window.toggleDistanceInput === 'function',
    downloadAndProcessActivity: typeof window.downloadAndProcessActivity === 'function',
    logout: typeof window.logout === 'function'
});