// Constants
const BACKEND_URL = "https://strim-production.up.railway.app";
const FRONTEND_URL = "https://strimrun.vercel.app";
const TOKEN_STORAGE_KEY = "strava_token";

// Global variables to track state
let selectedActivityId = null;
let selectedActivityDistance = null;

/**
 * Shows a message to the user with animation
 * @param {string} text - Message text
 * @param {string} type - Message type (success, error, info)
 */
function showMessage(text, type = "info") {
    const message = document.getElementById("message");
    if (!message) return;
    
    if (!text || text.trim() === "") {
        // If no message, fade out and hide the element
        message.classList.add("fadeOut");
        setTimeout(() => {
            message.textContent = "";
            message.style.display = "none";
            message.className = "";
        }, 300);
        return;
    }
    
    // Setup the message
    message.textContent = "";
    message.classList.remove("fadeOut");
    
    // Check if this is HTML content
    if (text.includes("<a") || text.includes("<div")) {
        message.innerHTML = text;
    } else {
        message.textContent = text;
    }
    
    message.className = type || "info";
    message.style.display = "block";
    
    // Auto-hide success and info messages after 3 seconds
    if (type === "success" || type === "info") {
        setTimeout(() => {
            // Only hide if it's still the same message
            if (message.textContent === text || message.innerHTML.includes(text)) {
                message.classList.add("fadeOut");
                setTimeout(() => {
                    message.textContent = "";
                    message.style.display = "none";
                }, 300);
            }
        }, 3000);
    }
}

/**
 * Get token from localStorage
 * @returns {string|null} The stored token or null
 */
function getStoredToken() {
    return localStorage.getItem(TOKEN_STORAGE_KEY);
}

/**
 * Store token in localStorage
 * @param {string} token - The token to store
 */
function storeToken(token) {
    if (token) {
        localStorage.setItem(TOKEN_STORAGE_KEY, token);
        console.log("✅ Token stored in localStorage");
    }
}

/**
 * Remove token from localStorage
 */
function clearToken() {
    localStorage.removeItem(TOKEN_STORAGE_KEY);
    console.log("🔄 Token removed from localStorage");
}

/**
 * Show authentication section, hide activity section
 */
function showAuthSection() {
    document.getElementById("authSection").classList.remove("hidden");
    document.getElementById("activitySection").classList.add("hidden");
}

/**
 * Show activity section, hide authentication section
 */
function showActivitySection() {
    document.getElementById("authSection").classList.add("hidden");
    document.getElementById("activitySection").classList.remove("hidden");
}

/**
 * Check authentication status and show appropriate section
 */
function checkAuthStatus() {
    console.log("Checking authentication status...");
    
    // Check for URL parameters from OAuth redirect
    const urlParams = new URLSearchParams(window.location.search);
    const authSuccess = urlParams.get("auth_success");
    const authError = urlParams.get("auth_error");
    const errorMsg = urlParams.get("message");
    const token = urlParams.get("token");
    
    // If token is in URL, store it
    if (token) {
        console.log("✅ Token found in URL parameters");
        storeToken(token);
    }
    
    // Remove query parameters from URL for cleaner appearance
    if (authSuccess || authError || token) {
        window.history.replaceState({}, document.title, window.location.pathname);
    }
    
    // Handle authentication error
    if (authError) {
        console.error(`❌ Authentication error: ${authError}`);
        showMessage(`Authentication failed: ${authError}${errorMsg ? ` (${errorMsg})` : ''}. Please try again.`, "error");
        showAuthSection();
        return;
    }
    
    // Handle successful authentication
    if (authSuccess === "true") {
        console.log("✅ Authentication successful");
        showMessage("Successfully connected with Strava!", "success");
        showActivitySection();
        fetchActivities();
        return;
    }
    
    // Check if we have a token in localStorage
    const storedToken = getStoredToken();
    if (storedToken) {
        console.log("✅ Found token in localStorage");
        showActivitySection();
        fetchActivities();
        return;
    }
    
    // No token, show auth section
    showAuthSection();
}

/**
 * Fetch user's activities from Strava
 */
async function fetchActivities() {
    try {
        console.log("Fetching activities...");

        // Show loading indicator
        document.getElementById("activityList").innerHTML = `
            <tr>
                <td colspan="4" style="text-align: center; padding: 20px;">
                    <i class="fas fa-running fa-spin" style="margin-right: 10px; color: var(--strava-orange);"></i>
                    Loading activities...
                </td>
            </tr>`;

        // Get token from localStorage
        const token = getStoredToken();
        
        if (!token) {
            console.error("No token available");
            showMessage("Authentication required. Please log in with Strava.", "error");
            showAuthSection();
            return;
        }
        
        // Create URL with token parameter only
        const url = `${BACKEND_URL}/activities?token=${encodeURIComponent(token)}`;
        console.log(`📡 Making request to: ${BACKEND_URL}/activities?token=***MASKED***`);

        // Make request without Authorization header to avoid CORS preflight
        const response = await fetch(url);

        if (!response.ok) {
            console.error(`Server error: ${response.status} ${response.statusText}`);
            
            if (response.status === 401) {
                clearToken();
                showMessage("Authentication expired. Please log in again.", "error");
                showAuthSection();
                return;
            }
            
            throw new Error(`Server returned ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();
        console.log(`✅ Retrieved ${data.activities ? data.activities.length : 0} activities`);

        // Update token if provided in response
        if (data.token) {
            storeToken(data.token);
        }

        // Display activities or show message if none found
        if (!data.activities || data.activities.length === 0) {
            document.getElementById("activityList").innerHTML = `
                <tr>
                    <td colspan="4" style="text-align: center; padding: 20px;">
                        <i class="fas fa-exclamation-circle" style="margin-right: 10px; color: var(--medium-gray);"></i>
                        No running activities found. Make sure you have running activities on Strava.
                    </td>
                </tr>`;
            return;
        }

        // Display activities in the table
        displayActivities(data.activities);
    } catch (error) {
        console.error("❌ Error fetching activities:", error);
        
        document.getElementById("activityList").innerHTML = `
            <tr>
                <td colspan="4" style="text-align: center; padding: 20px; color: var(--error-color);">
                    <i class="fas fa-exclamation-triangle" style="margin-right: 10px;"></i>
                    Failed to load activities: ${error.message}
                </td>
            </tr>`;
            
        showMessage(`Error loading activities: ${error.message}`, "error");
    }
}

/**
 * Display activities in the table with improved formatting
 * @param {Array} activities - List of activities
 */
function displayActivities(activities) {
    const activityList = document.getElementById("activityList");
    activityList.innerHTML = "";
    
    // Variable to track if we're showing all activities or just recent ones
    let showingAllActivities = false;
    
    // Function to render activities (either all or just recent ones)
    const renderActivities = (activitiesToShow) => {
        activityList.innerHTML = ""; // Clear the list first
        
        activitiesToShow.forEach(activity => {
            const row = document.createElement("tr");
            
            // Format date
            const activityDate = new Date(activity.date);
            const formattedDate = activityDate.toLocaleDateString(undefined, {
                year: 'numeric',
                month: 'short',
                day: 'numeric'
            });
            
            // Add activity type icon based on name
            let activityIcon = '';
            if (activity.name.toLowerCase().includes('night')) {
                activityIcon = '<i class="fas fa-moon"></i> ';
            } else if (activity.name.toLowerCase().includes('morning')) {
                activityIcon = '<i class="fas fa-sun"></i> ';
            } else if (activity.name.toLowerCase().includes('lunch')) {
                activityIcon = '<i class="fas fa-utensils"></i> ';
            } else {
                activityIcon = '<i class="fas fa-running"></i> ';
            }
            
            // Create activity display with "View on Strava" link separated below
            const activityDisplay = `
                <div class="activity-name">${activityIcon}${activity.name}</div>
                <a href="https://www.strava.com/activities/${activity.id}" target="_blank" class="strava-view-link">View on Strava</a>
            `;
            
            row.innerHTML = `
                <td>${activityDisplay}</td>
                <td>${activity.distance_miles.toFixed(2)}</td>
                <td>${formattedDate}</td>
                <td>
                    <input type="radio" 
                           name="selectedActivity" 
                           value="${activity.id}"
                           data-distance="${activity.distance_miles.toFixed(2)}">
                </td>
            `;
            
            activityList.appendChild(row);
            
            // Add click handler to the row
            row.addEventListener('click', function(e) {
                // If click was not directly on the radio button, find the radio and click it
                if (e.target.type !== 'radio') {
                    const radio = this.querySelector('input[type="radio"]');
                    if (radio) {
                        radio.checked = true;
                        selectActivity(activity.id, activity.distance_miles);
                    }
                }
            });
        });
        
        // Add "Show More/Less" row if there are more than 5 activities
        if (activities.length > 5) {
            const actionRow = document.createElement("tr");
            actionRow.className = "show-more-row";
            
            const actionText = showingAllActivities ? "Show Recent Activities" : "Show All Activities";
            const actionIcon = showingAllActivities ? "fa-chevron-up" : "fa-chevron-down";
            
            actionRow.innerHTML = `
                <td colspan="4">
                    <button id="toggleActivitiesBtn" class="toggle-activities-btn">
                        ${actionText} <i class="fas ${actionIcon}"></i>
                    </button>
                </td>
            `;
            
            activityList.appendChild(actionRow);
            
            // Add click handler to the button
            document.getElementById("toggleActivitiesBtn").addEventListener("click", function() {
                showingAllActivities = !showingAllActivities;
                if (showingAllActivities) {
                    renderActivities(activities); // Show all activities
                } else {
                    renderActivities(activities.slice(0, 5)); // Show only recent 5
                }
            });
        }
    };
    
    // Initial render - show only the 5 most recent activities
    renderActivities(activities.slice(0, 5));
}

/**
 * Select an activity
 * @param {string} id - Activity ID
 * @param {number} distance - Activity distance
 */
function selectActivity(id, distance) {
    selectedActivityId = id;
    selectedActivityDistance = distance;
    
    // Pre-fill distance field
    const distanceInput = document.getElementById("newDistance");
    if (distanceInput) {
        distanceInput.value = distance;
    }
    
    console.log(`Selected activity: ${id}, distance: ${distance} miles`);
    
    // Highlight the selected row
    const rows = document.querySelectorAll("#activityList tr");
    rows.forEach(row => {
        const radio = row.querySelector('input[type="radio"]');
        if (radio && radio.value === id) {
            row.classList.add('selected');
        } else {
            row.classList.remove('selected');
        }
    });
}

/**
 * Toggle distance input visibility with animation
 */
function toggleDistanceInput() {
    const editDistanceChecked = document.getElementById("editDistanceCheckbox").checked;
    const container = document.getElementById("distanceInputContainer");
    
    if (editDistanceChecked) {
        container.style.display = "block";
        container.style.maxHeight = "0";
        container.style.overflow = "hidden";
        
        // Trigger reflow
        void container.offsetWidth;
        
        // Animate open
        container.style.transition = "max-height 0.3s ease-in-out, opacity 0.3s ease-in-out";
        container.style.maxHeight = "100px";
        container.style.opacity = "0";
        setTimeout(() => {
            container.style.opacity = "1";
        }, 50);
    } else {
        // Animate close
        container.style.opacity = "0";
        container.style.maxHeight = "0";
        
        // Hide after animation
        setTimeout(() => {
            container.style.display = "none";
        }, 300);
    }
}

/**
 * Process selected activity
 */
async function trimActivity() {
    // Validate selection
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

    // Check if editing distance
    const editDistance = document.getElementById("editDistanceCheckbox").checked;
    let newDistance = null;
    
    if (editDistance) {
        newDistance = document.getElementById("newDistance").value;
        if (!newDistance || parseFloat(newDistance) <= 0) {
            showMessage("Please enter a valid distance greater than zero.", "error");
            return;
        }
    }

    try {
        // Disable button during processing
        const trimButton = document.getElementById("trimActivityButton");
        const originalButtonText = trimButton.innerHTML;
        trimButton.disabled = true;
        trimButton.innerHTML = `<i class="fas fa-spinner fa-spin"></i><span>Processing...</span>`;
        
        showMessage("Processing activity...", "info");

        // Get token from localStorage
        const token = getStoredToken();
        
        if (!token) {
            showMessage("Authentication required. Please log in with Strava.", "error");
            showAuthSection();
            return;
        }
        
        // Build URL with parameters
        let url = `${BACKEND_URL}/download-fit?activity_id=${selectedActivityId}`;
        
        if (editDistance) {
            url += `&edit_distance=true&new_distance=${encodeURIComponent(newDistance)}`;
        } else {
            url += `&edit_distance=false`;
        }
        
        // Add token as URL parameter
        url += `&token=${encodeURIComponent(token)}`;
        
        console.log(`📡 Making trim request: ${url.replace(token, "***MASKED***")}`);

        // Make request without Authorization header
        const response = await fetch(url);
        
        // Re-enable button
        trimButton.disabled = false;
        trimButton.innerHTML = originalButtonText;
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || `Failed to process activity (${response.status})`);
        }

        const result = await response.json();

        // Update token if provided
        if (result.token) {
            storeToken(result.token);
        }

        if (result.success) {
            // Show success message with link to view on Strava
            const messageDiv = document.createElement('div');
            messageDiv.innerHTML = `
                Activity successfully processed! 
                <a href="https://www.strava.com/activities/${result.new_activity_id}" 
                   target="_blank" style="margin-left: 10px; color: #FC5200; font-weight: bold; text-decoration: underline;">
                   View on Strava
                </a>
            `;
            
            const messageEl = document.getElementById('message');
            messageEl.innerHTML = '';
            messageEl.appendChild(messageDiv);
            messageEl.className = 'success';
            messageEl.style.display = 'block';
            
            // Refresh activities after a short delay
            setTimeout(fetchActivities, 1500);
        } else {
            throw new Error(result.error || "Unknown error occurred");
        }
    } catch (error) {
        console.error("Error processing activity:", error);
        showMessage(`Error: ${error.message}`, "error");
    }
}

/**
 * Log out user
 */
function logout() {
    console.log("Logging out...");
    showMessage("Logging out...", "info");
    
    // Clear the token
    clearToken();
    
    // Also call the backend logout endpoint
    fetch(`${BACKEND_URL}/logout`, {
        method: "POST"
    }).catch(error => {
        console.error("Error calling logout endpoint:", error);
    }).finally(() => {
        showAuthSection();
        showMessage("Logged out successfully", "success");
    });
}

/**
 * Direct to Strava authentication
 */
function loginWithStrava() {
    window.location.href = `${BACKEND_URL}/auth`;
}

// Initialize the app when the document is loaded
document.addEventListener("DOMContentLoaded", function() {
    console.log("Document loaded, initializing app...");
    
    // Initialize the message element
    const message = document.getElementById("message");
    if (message) {
        message.style.display = "none";
        message.textContent = "";
    }
    
    // Set up event listeners
    
    // Strava auth link
    const stravaAuthLink = document.getElementById("stravaAuthLink");
    if (stravaAuthLink) {
        stravaAuthLink.addEventListener("click", function(e) {
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
    
    // Check authentication status
    checkAuthStatus();
});

// Expose functions to the global scope
window.selectActivity = selectActivity;
window.toggleDistanceInput = toggleDistanceInput;
window.trimActivity = trimActivity;
window.logout = logout;
window.loginWithStrava = loginWithStrava;