// Import configuration from module
import config from './config.js';

// Get backend and frontend URLs from config
const BACKEND_URL = config.getBackendURL();
const FRONTEND_URL = config.getFrontendURL();

// Token storage key
const TOKEN_STORAGE_KEY = 'strava_token';

// Global variables for selected activity
let selectedActivityId = null;
let selectedActivityDistance = null;

/**
 * Show a message to the user with improved handling of empty messages
 * @param {string} text - The message text to display
 * @param {string} type - The message type (success, error, info)
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
    
    // Auto-hide success and info messages after 5 seconds
    if (type === "success" || type === "info") {
        setTimeout(() => {
            if (message.textContent === text) {
                message.style.display = "none";
            }
        }, 5000);
    }
}

/**
 * Get stored authentication token
 * @returns {string|null} - The stored token or null if not found
 */
function getStoredToken() {
    return localStorage.getItem(TOKEN_STORAGE_KEY);
}

/**
 * Store authentication token
 * @param {string} token - The token to store
 */
function storeToken(token) {
    if (token) {
        localStorage.setItem(TOKEN_STORAGE_KEY, token);
        console.log("✅ Token stored in localStorage");
    }
}

/**
 * Clear stored authentication token
 */
function clearToken() {
    localStorage.removeItem(TOKEN_STORAGE_KEY);
    console.log("🔄 Token removed from localStorage");
}

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
    const token = urlParams.get("token");
    
    // If token is in URL, store it
    if (token) {
        console.log("✅ Token found in URL, storing in localStorage");
        storeToken(token);
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
        
        // Ensure auth section is visible
        showAuthSection();
        return;
    }
    
    // If auth_success=true is in URL, we just completed authentication
    if (authSuccess === "true") {
        console.log("✅ Authentication successful from redirect");
        
        // Show a success message briefly
        showMessage("Successfully authenticated with Strava!", "success");
        
        // Show activity section and fetch activities
        showActivitySection();
        fetchActivities();
        return;
    }
    
    // Check if we have a token in localStorage
    const storedToken = getStoredToken();
    if (storedToken) {
        console.log("✅ Found token in localStorage, using it");
        showActivitySection();
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
            showAuthSection();
            return null;
        }
        return response.json();
    })
    .then(data => {
        if (!data) return; // Skip if response wasn't ok
        
        console.log("Auth status response:", data);
        if (data.authenticated) {
            console.log("✅ User is authenticated");
            
            // Store token in localStorage if provided
            if (data.token) {
                console.log("✅ Storing token from session in localStorage");
                storeToken(data.token);
            }
            
            // Show the activity section
            showActivitySection();
            fetchActivities();
        } else {
            console.log(`❌ User is NOT authenticated: ${data.reason || 'unknown reason'}`);
            showAuthSection();
        }
    })
    .catch(error => {
        console.error("Error checking auth status:", error);
        showAuthSection();
    });
}

/**
 * Show authentication section and hide activity section
 */
function showAuthSection() {
    document.getElementById("authSection").classList.remove("hidden");
    document.getElementById("activitySection").classList.add("hidden");
}

/**
 * Show activity section and hide authentication section
 */
function showActivitySection() {
    document.getElementById("authSection").classList.add("hidden");
    document.getElementById("activitySection").classList.remove("hidden");
}

/**
 * Fetch user's activities from Strava
 */
async function fetchActivities() {
    try {
        console.log("Fetching activities...");

        // Show loading indicator
        document.getElementById("activityList").innerHTML = "<tr><td colspan='4'>Loading activities...</td></tr>";

        // Get token from localStorage
        const token = getStoredToken();
        
        // Create URL with token parameter
        const url = token 
            ? `${BACKEND_URL}/activities?token=${encodeURIComponent(token)}` 
            : `${BACKEND_URL}/activities`;
            
        console.log(`📡 Making request to: ${token ? `${BACKEND_URL}/activities?token=***MASKED***` : url}`);

        // Make request WITHOUT Authorization header since we're using URL parameter
        const response = await fetch(url, {
            method: "GET",
            credentials: "include"  // Still include credentials for cookies
            // No Authorization header
        });
        
        if (!response.ok) {
            console.error(`❌ Error fetching activities: ${response.status} ${response.statusText}`);

            if (response.status === 401) {
                console.log("Session expired, showing login prompt");
                clearToken(); // Clear invalid token
                showMessage("Session expired. Please log in again.", "error");
                
                // Wait a moment before redirecting
                setTimeout(() => {
                    showAuthSection();
                }, 2000);
            } else {
                document.getElementById("activityList").innerHTML = 
                    `<tr><td colspan='4'>Error loading activities: ${response.status} ${response.statusText}</td></tr>`;
            }
            return;
        }

        const data = await response.json();
        console.log("✅ Fetched activities:", data);

        // If token is in the response, store it
        if (data.token) {
            console.log("✅ Updating token from activities response");
            storeToken(data.token);
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
                <td>
                    <input type="radio" 
                           name="selectedActivity" 
                           value="${activity.id}" 
                           data-distance="${activity.distance_miles.toFixed(2)}"
                           onchange="window.selectActivity('${activity.id}', ${activity.distance_miles.toFixed(2)})">
                </td>
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
 * Set selected activity
 * @param {string} id - Activity ID
 * @param {number} distance - Activity distance in miles
 */
function selectActivity(id, distance) {
    selectedActivityId = id;
    selectedActivityDistance = distance;
    
    // Set the current distance as the default value for the input field
    const distanceInput = document.getElementById("newDistance");
    if (distanceInput) {
        distanceInput.value = distance;
    }
    
    console.log(`Selected activity: ${id}, distance: ${distance} miles`);
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
async function trimActivity() {
    // Check if an activity is selected
    if (!selectedActivityId) {
        const selectedRadio = document.querySelector('input[name="selectedActivity"]:checked');
        if (selectedRadio) {
            selectedActivityId = selectedRadio.value;
            selectedActivityDistance = parseFloat(selectedRadio.getAttribute('data-distance'));
        } else {
            showMessage("Please select an activity first.", "error");
            return;
        }
    }

    const editDistance = document.getElementById("editDistanceCheckbox").checked;
    let newDistance = editDistance ? document.getElementById("newDistance").value : null;

    if (editDistance && (!newDistance || parseFloat(newDistance) <= 0)) {
        showMessage("Please enter a valid new distance (greater than zero).", "error");
        return;
    }

    try {
        // Disable the trim button to prevent double submissions
        const trimButton = document.getElementById("trimActivityButton");
        const originalButtonText = trimButton.textContent;
        trimButton.disabled = true;
        trimButton.textContent = "Processing...";
        
        showMessage("Downloading and processing activity...", "info");

        // Get token from localStorage
        const token = getStoredToken();
        
        // Build the URL with parameters
        let url = `${BACKEND_URL}/download-fit?activity_id=${selectedActivityId}`;
        
        if (editDistance) {
            url += `&edit_distance=true&new_distance=${encodeURIComponent(newDistance)}`;
        } else {
            url += `&edit_distance=false`;
        }
        
        if (token) {
            url += `&token=${encodeURIComponent(token)}`;
        }

        const headers = token && !url.includes('token=') 
        ? { 'Authorization': `Bearer ${token}` } 
        : {};

        // Make the request
        const response = await fetch(url, {
            method: "GET",
            credentials: "include",
            headers: headers
        });
        
        // Re-enable the button
        trimButton.disabled = false;
        trimButton.textContent = originalButtonText;
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || `Failed to process activity (${response.status})`);
        }

        const result = await response.json();

        if (result.success) {
            showMessage("Activity successfully trimmed and uploaded to Strava!", "success");
            
            // Add prompt to view on Strava
            const viewOnStravaButton = document.createElement('button');
            viewOnStravaButton.textContent = 'View on Strava';
            viewOnStravaButton.style.marginLeft = '10px';
            viewOnStravaButton.onclick = () => {
                window.open(`https://www.strava.com/activities/${result.new_activity_id}`, '_blank');
            };
            
            // Append the button to the message
            document.getElementById('message').appendChild(viewOnStravaButton);
            
            // Refresh activities list with slight delay
            setTimeout(fetchActivities, 2000);
        } else {
            throw new Error(result.error || "Unknown error occurred");
        }
    } catch (error) {
        console.error("Error processing activity:", error);
        showMessage(`Error: ${error.message}`, "error");
    }
}

/**
 * Handle logout - clears local storage and session
 */
function logout() {
    console.log("🔴 Logging out...");
    showMessage("Logging out...", "info");
    
    // Clear the token from localStorage
    clearToken();
    
    // Call the logout endpoint
    fetch(`${BACKEND_URL}/logout`, {
        method: "POST",
        credentials: "include" // Send cookies
    })
    .then(() => {
        showMessage("Logged out successfully", "success");
        setTimeout(() => {
            // Show login page
            showAuthSection();
        }, 1000);
    })
    .catch(error => {
        console.error("Error logging out:", error);
        showMessage("Error logging out", "error");
        setTimeout(() => {
            showAuthSection();
        }, 1000);
    });
}

/**
 * Direct to Strava authentication
 */
function loginWithStrava() {
    window.location.href = `${BACKEND_URL}/auth`;
}

/**
 * Initialize the application
 */
function initializeApp() {
    console.log("Initializing app...");
    console.log(`Backend URL: ${BACKEND_URL}`);
    console.log(`Frontend URL: ${FRONTEND_URL}`);
    
    // Initialize message container
    const message = document.getElementById("message");
    if (message) {
        message.style.display = "none";
        message.textContent = "";
    }
    
    // Set up event listeners
    
    // Auth link
    const stravaAuthLink = document.getElementById("stravaAuthLink");
    if (stravaAuthLink) {
        stravaAuthLink.addEventListener("click", (e) => {
            e.preventDefault();
            loginWithStrava();
        });
    }
    
    // Edit distance checkbox
    const editDistanceCheckbox = document.getElementById("editDistanceCheckbox");
    if (editDistanceCheckbox) {
        editDistanceCheckbox.addEventListener("change", toggleDistanceInput);
    }
    
    // Trim activity button
    const trimButton = document.getElementById("trimActivityButton");
    if (trimButton) {
        trimButton.addEventListener("click", trimActivity);
    }
    
    // Logout button
    const logoutButton = document.getElementById("logoutButton");
    if (logoutButton) {
        logoutButton.addEventListener("click", logout);
    }
    
    // Check auth status
    checkAuthStatus();
}

// Initialize when the document is loaded
document.addEventListener("DOMContentLoaded", initializeApp);

// Make sure key functions are exposed to the global scope
window.toggleDistanceInput = toggleDistanceInput;
window.trimActivity = trimActivity;
window.logout = logout;
window.selectActivity = selectActivity;

// Export functions
export {
    showMessage,
    checkAuthStatus,
    fetchActivities,
    toggleDistanceInput,
    trimActivity,
    logout
};