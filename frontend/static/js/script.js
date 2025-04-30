// Constants
const BACKEND_URL = "https://strim-production.up.railway.app";
const FRONTEND_URL = "https://strimrun.vercel.app";
const TOKEN_STORAGE_KEY = "strava_token";

// Global variables to track state
let selectedActivityId = null;
let selectedActivityDistance = null;

// Global variables for activity visualization
let activityData = null;
let paceChart = null;
let trimStartIndex = 0;
let trimEndIndex = 0;
let showingPace = true; // true for pace, false for speed
let originalMetrics = {
  distance: 0,
  time: 0,
  pace: 0,
};
let editedMetrics = {
  distance: 0,
  time: 0,
  pace: 0,
};

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

  // Hide the steps section when showing activities
  const stepsSection = document.querySelector(".steps");
  if (stepsSection) {
    stepsSection.classList.add("hidden");
  }
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
    showMessage(
      `Authentication failed: ${authError}${
        errorMsg ? ` (${errorMsg})` : ""
      }. Please try again.`,
      "error"
    );
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
      showMessage(
        "Authentication required. Please log in with Strava.",
        "error"
      );
      showAuthSection();
      return;
    }

    // Create URL with token parameter only
    const url = `${BACKEND_URL}/activities?token=${encodeURIComponent(token)}`;
    console.log(
      `📡 Making request to: ${BACKEND_URL}/activities?token=***MASKED***`
    );

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

      throw new Error(
        `Server returned ${response.status}: ${response.statusText}`
      );
    }

    const data = await response.json();
    console.log(
      `✅ Retrieved ${data.activities ? data.activities.length : 0} activities`
    );

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

    activitiesToShow.forEach((activity) => {
      const row = document.createElement("tr");

      // Format date
      const activityDate = new Date(activity.date);
      const formattedDate = activityDate.toLocaleDateString(undefined, {
        year: "numeric",
        month: "short",
        day: "numeric",
      });

      // Add activity type icon based on name
      let activityIcon = "";
      if (activity.name.toLowerCase().includes("night")) {
        activityIcon = '<i class="fas fa-moon"></i> ';
      } else if (activity.name.toLowerCase().includes("morning")) {
        activityIcon = '<i class="fas fa-sun"></i> ';
      } else if (activity.name.toLowerCase().includes("lunch")) {
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
                           data-distance="${activity.distance_miles.toFixed(
                             2
                           )}">
                </td>
            `;

      activityList.appendChild(row);

      // Add click handler to the row
      row.addEventListener("click", function (e) {
        // If click was not directly on the radio button, find the radio and click it
        if (e.target.type !== "radio") {
          const radio = this.querySelector('input[type="radio"]');
          if (radio) {
            radio.checked = true;
            // Manually trigger the change event on the radio button
            const changeEvent = new Event("change", { bubbles: true });
            radio.dispatchEvent(changeEvent);
          }
        }
      });

      // Add direct event handler to the radio button itself
      const radio = row.querySelector('input[type="radio"]');
      if (radio) {
        radio.addEventListener("change", function () {
          if (this.checked) {
            // Select the activity and load the visualization
            selectActivity(activity.id, activity.distance_miles);
          }
        });
      }
    });

    // Add "Show More/Less" row if there are more than 5 activities
    if (activities.length > 5) {
      const actionRow = document.createElement("tr");
      actionRow.className = "show-more-row";

      const actionText = showingAllActivities
        ? "Show Recent Activities"
        : "Show All Activities";
      const actionIcon = showingAllActivities
        ? "fa-chevron-up"
        : "fa-chevron-down";

      actionRow.innerHTML = `
                <td colspan="4">
                    <button id="toggleActivitiesBtn" class="show-recent-button">
                        <i class="fas ${actionIcon}"></i><span>${actionText}</span>
                    </button>
                </td>
            `;

      activityList.appendChild(actionRow);

      // Add click handler to the button
      document
        .getElementById("toggleActivitiesBtn")
        .addEventListener("click", function () {
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
 * Handle activity selection with visualization
 */
function selectActivity(activityId, activityDistance) {
  selectedActivityId = activityId;
  selectedActivityDistance = activityDistance;

  // Pre-fill distance field
  const distanceInput = document.getElementById("newDistance");
  if (distanceInput) {
    distanceInput.value = activityDistance;
  }

  console.log(
    `Selected activity: ${activityId}, distance: ${activityDistance} miles`
  );

  // Highlight the selected row
  const rows = document.querySelectorAll("#activityList tr");
  rows.forEach((row) => {
    const radio = row.querySelector('input[type="radio"]');
    if (radio && radio.value === activityId) {
      row.classList.add("selected");
    } else {
      row.classList.remove("selected");
    }
  });

  // Check if activity has photos and show warning if needed
  checkForPhotos(activityId);

  // Update radio button selection
  const radioButtons = document.querySelectorAll(
    'input[name="selectedActivity"]'
  );
  radioButtons.forEach((radio) => {
    if (radio.value === activityId) {
      radio.checked = true;
    } else {
      radio.checked = false;
    }
  });

  // Reset visualization data
  activityData = null;
  if (paceChart) {
    paceChart.destroy();
    paceChart = null;
  }

  // Reset metrics
  originalMetrics = { distance: 0, time: 0, pace: 0 };
  editedMetrics = { distance: 0, time: 0, pace: 0 };

  // Hide visualization container
  document.getElementById("activityVisualization").style.display = "none";

  // Load activity data
  loadActivityVisualization(activityId);
}

/**
 * Toggle distance input visibility with animation
 */
function toggleDistanceInput() {
  const editDistanceChecked = document.getElementById(
    "editDistanceCheckbox"
  ).checked;
  const container = document.getElementById("distanceInputContainer");

  if (editDistanceChecked) {
    container.style.display = "block";
    container.style.maxHeight = "0";
    container.style.overflow = "hidden";

    // Trigger reflow
    void container.offsetWidth;

    // Animate open
    container.style.transition =
      "max-height 0.3s ease-in-out, opacity 0.3s ease-in-out";
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

function checkForPhotos(activityId) {
  // Get token from localStorage
  const token = getStoredToken();

  if (!token || !activityId) {
    return;
  }

  // Create URL with token parameter
  const url = `${BACKEND_URL}/activities/${activityId}/details?token=${encodeURIComponent(
    token
  )}`;

  // Make request to get activity details
  fetch(url)
    .then((response) => {
      if (!response.ok) {
        throw new Error(
          `Server returned ${response.status}: ${response.statusText}`
        );
      }
      return response.json();
    })
    .then((data) => {
      // Check if the activity has photos
      if (
        data.activity &&
        data.activity.photos &&
        data.activity.photos.count > 0
      ) {
        // Show photo warning message
        const warningDiv = document.getElementById("photoWarning");
        if (warningDiv) {
          warningDiv.classList.remove("hidden");
        }
      } else {
        // Hide photo warning if no photos
        const warningDiv = document.getElementById("photoWarning");
        if (warningDiv) {
          warningDiv.classList.add("hidden");
        }
      }
    })
    .catch((error) => {
      console.error("Error checking for photos:", error);
    });
}

/**
 * Process selected activity
 */
async function trimActivity() {
  // Validate selection
  if (!selectedActivityId) {
    const selectedRadio = document.querySelector(
      'input[name="selectedActivity"]:checked'
    );
    if (selectedRadio) {
      selectedActivityId = selectedRadio.value;
      selectedActivityDistance = parseFloat(
        selectedRadio.getAttribute("data-distance")
      );
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
      showMessage(
        "Authentication required. Please log in with Strava.",
        "error"
      );
      showAuthSection();
      return;
    }

    // Build URL with parameters
    let url = `${BACKEND_URL}/download-fit?activity_id=${selectedActivityId}`;

    // Add trim indices if available from visualization
    if (activityData && activityData.pace_data) {
      // If user has adjusted the trim markers, send the data points
      if (
        trimStartIndex > 0 ||
        trimEndIndex < activityData.pace_data.length - 1
      ) {
        const startTimeData = activityData.pace_data[trimStartIndex];
        const endTimeData = activityData.pace_data[trimEndIndex];

        if (startTimeData && endTimeData) {
          // Add time points for trimming
          url += `&trim_start_time=${startTimeData.time}&trim_end_time=${endTimeData.time}`;
          console.log(
            `Sending manual trim points: ${startTimeData.time} to ${endTimeData.time} seconds`
          );
        }
      }
    }

    if (editDistance) {
      url += `&edit_distance=true&new_distance=${encodeURIComponent(
        newDistance
      )}`;
    } else {
      url += `&edit_distance=false`;
    }

    // Add token as URL parameter
    url += `&token=${encodeURIComponent(token)}`;

    console.log(
      `📡 Making trim request: ${url.replace(token, "***MASKED***")}`
    );

    // Make request without Authorization header
    const response = await fetch(url);

    // Re-enable button
    trimButton.disabled = false;
    trimButton.innerHTML = originalButtonText;

    if (!response.ok) {
      try {
        const errorData = await response.json();

        // Check if this is a Python traceback error
        if (errorData.error && errorData.error.includes("traceback")) {
          console.error("Backend error (traceback):", errorData.error);
          throw new Error(
            "Server error: The backend encountered an issue with traceback. Please try again later."
          );
        } else {
          throw new Error(
            errorData.error || `Failed to process activity (${response.status})`
          );
        }
      } catch (jsonError) {
        // If we can't parse the error as JSON, show a generic error
        throw new Error(
          `Server error (${response.status}): Please try again later.`
        );
      }
    }

    const result = await response.json();

    // Update token if provided
    if (result.token) {
      storeToken(result.token);
    }

    if (result.success) {
      // Show success message with link to view on Strava
      const messageDiv = document.createElement("div");
      messageDiv.innerHTML = `
                Activity successfully processed! 
                <a href="https://www.strava.com/activities/${result.new_activity_id}" 
                   target="_blank" style="margin-left: 10px; color: #FC5200; font-weight: bold; text-decoration: underline;">
                   View on Strava
                </a>
            `;

      const messageEl = document.getElementById("message");
      messageEl.innerHTML = "";
      messageEl.appendChild(messageDiv);
      messageEl.className = "success";
      messageEl.style.display = "block";

      // Set a flag to indicate success to prevent overriding with error messages
      window.lastActivityTrimSuccess = true;

      // Refresh activities after a short delay
      setTimeout(fetchActivities, 1500);
    } else {
      throw new Error(result.error || "Unknown error occurred");
    }
  } catch (error) {
    console.error("Error processing activity:", error);

    // Only show error message if we didn't just show a success message
    if (!window.lastActivityTrimSuccess) {
      showMessage(`Error: ${error.message}`, "error");
    } else {
      // If we had a success but still got an error (like a timeout),
      // just log it without showing to user
      console.log("Suppressing error after successful trim:", error.message);
    }
  } finally {
    // Reset the success flag after a short delay
    setTimeout(() => {
      window.lastActivityTrimSuccess = false;
    }, 3000);
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
    method: "POST",
  })
    .catch((error) => {
      console.error("Error calling logout endpoint:", error);
    })
    .finally(() => {
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
document.addEventListener("DOMContentLoaded", function () {
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
    stravaAuthLink.addEventListener("click", function (e) {
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

/**
 * Format seconds into a readable time string (MM:SS or HH:MM:SS)
 */
function formatTime(seconds) {
  if (!seconds) return "--";

  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = Math.floor(seconds % 60);

  if (hours > 0) {
    return `${hours}:${minutes.toString().padStart(2, "0")}:${secs
      .toString()
      .padStart(2, "0")}`;
  } else {
    return `${minutes}:${secs.toString().padStart(2, "0")}`;
  }
}

/**
 * Format distance (km or miles)
 */
function formatDistance(meters, isMetric = false) {
  if (!meters) return "--";

  if (isMetric) {
    const km = meters / 1000;
    return `${km.toFixed(2)} km`;
  } else {
    const miles = meters / 1609.34;
    return `${miles.toFixed(2)} mi`;
  }
}

/**
 * Format pace (min/km or min/mile)
 */
function formatPace(secondsPerMeter, isMetric = false) {
  if (!secondsPerMeter || secondsPerMeter <= 0) return "--";

  let secondsPerUnit;
  if (isMetric) {
    // min/km
    secondsPerUnit = secondsPerMeter * 1000;
  } else {
    // min/mile
    secondsPerUnit = secondsPerMeter * 1609.34;
  }

  const minutes = Math.floor(secondsPerUnit / 60);
  const seconds = Math.floor(secondsPerUnit % 60);

  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

/**
 * Calculate pace from speed
 */
function calculatePace(speedMps) {
  if (!speedMps || speedMps <= 0) return 0;
  return 1 / speedMps; // seconds per meter
}

/**
 * Update the before/after comparison table
 */
function updateComparisonTable() {
  // Get elements
  const originalDistanceEl = document.getElementById("originalDistance");
  const editedDistanceEl = document.getElementById("editedDistance");
  const distanceDiffEl = document.getElementById("distanceDiff");

  const originalTimeEl = document.getElementById("originalTime");
  const editedTimeEl = document.getElementById("editedTime");
  const timeDiffEl = document.getElementById("timeDiff");

  const originalPaceEl = document.getElementById("originalPace");
  const editedPaceEl = document.getElementById("editedPace");
  const paceDiffEl = document.getElementById("paceDiff");

  // Get metrics
  const isMetric = activityData?.activity?.is_metric || false;

  // Update original values
  originalDistanceEl.textContent = formatDistance(
    originalMetrics.distance,
    isMetric
  );
  originalTimeEl.textContent = formatTime(originalMetrics.time);
  originalPaceEl.textContent = formatPace(originalMetrics.pace, isMetric);

  // Update edited values
  editedDistanceEl.textContent = formatDistance(
    editedMetrics.distance,
    isMetric
  );
  editedTimeEl.textContent = formatTime(editedMetrics.time);
  editedPaceEl.textContent = formatPace(editedMetrics.pace, isMetric);

  // Calculate and update differences
  const distanceDiff = editedMetrics.distance - originalMetrics.distance;
  const timeDiff = editedMetrics.time - originalMetrics.time;
  const paceDiff = editedMetrics.pace - originalMetrics.pace;

  // Format and display difference values
  if (distanceDiff !== 0) {
    const distanceUnit = isMetric ? "km" : "mi";
    const formattedDiff = isMetric
      ? (distanceDiff / 1000).toFixed(2)
      : (distanceDiff / 1609.34).toFixed(2);

    distanceDiffEl.textContent = `${
      formattedDiff > 0 ? "+" : ""
    }${formattedDiff} ${distanceUnit}`;
    distanceDiffEl.className =
      distanceDiff > 0 ? "difference positive" : "difference negative";
  } else {
    distanceDiffEl.textContent = "--";
    distanceDiffEl.className = "difference";
  }

  if (timeDiff !== 0) {
    const sign = timeDiff > 0 ? "+" : "";
    const formattedTimeDiff = formatTime(Math.abs(timeDiff));
    timeDiffEl.textContent = `${sign}${formattedTimeDiff}`;
    timeDiffEl.className =
      timeDiff > 0 ? "difference negative" : "difference positive";
  } else {
    timeDiffEl.textContent = "--";
    timeDiffEl.className = "difference";
  }

  if (paceDiff !== 0 && originalMetrics.pace > 0 && editedMetrics.pace > 0) {
    // Calculate percentage change in pace
    const pacePercentChange =
      ((editedMetrics.pace - originalMetrics.pace) / originalMetrics.pace) *
      100;

    // For pace, lower is better (faster)
    const isFaster = paceDiff < 0;
    paceDiffEl.textContent = `${isFaster ? "" : "+"}${Math.abs(
      pacePercentChange
    ).toFixed(1)}%`;
    paceDiffEl.className = isFaster
      ? "difference positive"
      : "difference negative";
  } else {
    paceDiffEl.textContent = "--";
    paceDiffEl.className = "difference";
  }
}

/**
 * Create the pace/speed chart
 */
function createPaceChart() {
  if (
    !activityData ||
    !activityData.pace_data ||
    activityData.pace_data.length === 0
  ) {
    console.log("No pace data available for chart");
    return;
  }

  const ctx = document.getElementById("paceChart").getContext("2d");

  // Default to pace view and non-metric
  const isMetric = activityData.activity.is_metric || false;

  // Prepare data for the chart
  const labels = activityData.pace_data.map((d) => d.minutes);

  // For pace (lower is better)
  const paceData = activityData.pace_data.map((d) => {
    if (d.velocity <= 0) return null; // Skip points with zero velocity

    // Convert m/s to min/km or min/mile
    const secondsPerMeter = 1 / d.velocity;
    return isMetric
      ? (secondsPerMeter * 1000) / 60 // min/km
      : (secondsPerMeter * 1609.34) / 60; // min/mile
  });

  // For speed (higher is better)
  const speedData = activityData.pace_data.map((d) => {
    if (d.velocity <= 0) return null;

    // Convert m/s to km/h or mph
    return isMetric
      ? d.velocity * 3.6 // km/h
      : d.velocity * 2.237; // mph
  });

  // Create the chart
  paceChart = new Chart(ctx, {
    type: "line",
    data: {
      labels: labels,
      datasets: [
        {
          label: isMetric ? "Pace (min/km)" : "Pace (min/mile)",
          data: paceData,
          borderColor: "rgba(252, 76, 2, 0.7)",
          backgroundColor: "rgba(252, 76, 2, 0.1)",
          pointRadius: 0,
          borderWidth: 2,
          tension: 0.1,
          fill: false,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: {
          type: "linear",
          title: {
            display: true,
            text: "Time (minutes)",
          },
          grid: {
            color: "rgba(0, 0, 0, 0.05)",
          },
        },
        y: {
          reverse: true, // For pace, lower is better
          title: {
            display: true,
            text: isMetric ? "Pace (min/km)" : "Pace (min/mile)",
          },
          grid: {
            color: "rgba(0, 0, 0, 0.05)",
          },
        },
      },
      plugins: {
        tooltip: {
          enabled: true,
          mode: "index",
          intersect: false,
          callbacks: {
            label: function (context) {
              const value = context.raw;
              if (value == null) return "";

              const minutes = Math.floor(value);
              const seconds = Math.floor((value - minutes) * 60);
              return `Pace: ${minutes}:${seconds.toString().padStart(2, "0")}`;
            },
          },
        },
        legend: {
          display: false,
        },
      },
      interaction: {
        mode: "nearest",
        axis: "x",
        intersect: false,
      },
    },
  });

  // Initialize trim markers
  trimStartIndex = 0;
  trimEndIndex = activityData.pace_data.length - 1;
  updateTrimMarkers();

  // Show the visualization section
  document.getElementById("activityVisualization").style.display = "block";
}

/**
 * Toggle between pace and speed views
 */
function togglePaceSpeedView() {
  if (!paceChart || !activityData) return;

  showingPace = !showingPace;
  const isMetric = activityData.activity.is_metric || false;

  // Update toggle button UI
  const paceOption = document.querySelector(
    '.toggle-option[data-option="pace"]'
  );
  const speedOption = document.querySelector(
    '.toggle-option[data-option="speed"]'
  );

  if (showingPace) {
    paceOption.classList.add("active");
    speedOption.classList.remove("active");
  } else {
    paceOption.classList.remove("active");
    speedOption.classList.add("active");
  }

  // Update chart data and options
  if (showingPace) {
    // Convert back to pace
    paceChart.data.datasets[0].label = isMetric
      ? "Pace (min/km)"
      : "Pace (min/mile)";

    // Convert velocity to pace
    paceChart.data.datasets[0].data = activityData.pace_data.map((d) => {
      if (d.velocity <= 0) return null;
      const secondsPerMeter = 1 / d.velocity;
      return isMetric
        ? (secondsPerMeter * 1000) / 60 // min/km
        : (secondsPerMeter * 1609.34) / 60; // min/mile
    });

    // For pace, reverse the Y axis (lower is better)
    paceChart.options.scales.y.reverse = true;
    paceChart.options.scales.y.title.text = isMetric
      ? "Pace (min/km)"
      : "Pace (min/mile)";

    // Update tooltip
    paceChart.options.plugins.tooltip.callbacks.label = function (context) {
      const value = context.raw;
      if (value == null) return "";

      const minutes = Math.floor(value);
      const seconds = Math.floor((value - minutes) * 60);
      return `Pace: ${minutes}:${seconds.toString().padStart(2, "0")}`;
    };
  } else {
    // Convert to speed
    paceChart.data.datasets[0].label = isMetric
      ? "Speed (km/h)"
      : "Speed (mph)";

    // Convert velocity to speed
    paceChart.data.datasets[0].data = activityData.pace_data.map((d) => {
      if (d.velocity <= 0) return null;
      return isMetric
        ? d.velocity * 3.6 // km/h
        : d.velocity * 2.237; // mph
    });

    // For speed, don't reverse the Y axis (higher is better)
    paceChart.options.scales.y.reverse = false;
    paceChart.options.scales.y.title.text = isMetric
      ? "Speed (km/h)"
      : "Speed (mph)";

    // Update tooltip
    paceChart.options.plugins.tooltip.callbacks.label = function (context) {
      const value = context.raw;
      if (value == null) return "";

      return `Speed: ${value.toFixed(1)} ${isMetric ? "km/h" : "mph"}`;
    };
  }

  // Update the chart
  paceChart.update();
}

/**
 * Initialize marker dragging
 */
function initMarkerDrag() {
  const startMarker = document.getElementById("startMarker");
  const endMarker = document.getElementById("endMarker");
  const chartContainer = document.querySelector(".canvas-container");

  let activeMarker = null;
  let initialX = 0;
  let chartRect = null;

  // Start drag
  const startDrag = function (e) {
    activeMarker = e.target;
    initialX = e.clientX || (e.touches && e.touches[0].clientX);
    chartRect = chartContainer.getBoundingClientRect();

    document.addEventListener("mousemove", doDrag);
    document.addEventListener("touchmove", doDrag);
    document.addEventListener("mouseup", endDrag);
    document.addEventListener("touchend", endDrag);

    e.preventDefault();
  };

  // During drag
  const doDrag = function (e) {
    if (!activeMarker) return;

    const clientX = e.clientX || (e.touches && e.touches[0].clientX);
    const offsetX = clientX - chartRect.left;
    const containerWidth = chartRect.width;

    // Calculate position as percentage
    let positionPercent = (offsetX / containerWidth) * 100;

    // Constrain within bounds (0-100%)
    positionPercent = Math.max(0, Math.min(100, positionPercent));

    // Make sure start marker is before end marker
    if (activeMarker === startMarker) {
      const endPercent = parseFloat(endMarker.style.left);
      positionPercent = Math.min(positionPercent, endPercent - 2);
      startMarker.style.left = `${positionPercent}%`;
    } else {
      const startPercent = parseFloat(startMarker.style.left);
      positionPercent = Math.max(positionPercent, startPercent + 2);
      endMarker.style.left = `${positionPercent}%`;
    }

    // Update chart highlighting
    updateTrimHighlighting();

    // Update metrics
    updateTrimmedMetrics();

    e.preventDefault();
  };

  // End drag
  const endDrag = function (e) {
    activeMarker = null;
    document.removeEventListener("mousemove", doDrag);
    document.removeEventListener("touchmove", doDrag);
    document.removeEventListener("mouseup", endDrag);
    document.removeEventListener("touchend", endDrag);
  };

  // Add event listeners
  startMarker.addEventListener("mousedown", startDrag);
  startMarker.addEventListener("touchstart", startDrag);
  endMarker.addEventListener("mousedown", startDrag);
  endMarker.addEventListener("touchstart", startDrag);
}

/**
 * Update trim markers positions
 */
function updateTrimMarkers() {
  if (!activityData || !activityData.pace_data) return;

  const startMarker = document.getElementById("startMarker");
  const endMarker = document.getElementById("endMarker");

  const totalPoints = activityData.pace_data.length;
  if (totalPoints === 0) return;

  // Set initial positions (start at 0%, end at 100%)
  startMarker.style.left = "0%";
  endMarker.style.left = "100%";

  // Update the chart highlighting
  updateTrimHighlighting();

  // Calculate and update metrics
  updateTrimmedMetrics();
}

/**
 * Update chart highlighting for the trimmed section
 */
function updateTrimHighlighting() {
  if (!paceChart) return;

  const startMarker = document.getElementById("startMarker");
  const endMarker = document.getElementById("endMarker");

  // Get positions as percentages
  const startPercent = parseFloat(startMarker.style.left);
  const endPercent = parseFloat(endMarker.style.left);

  // Convert percentages to data indices
  const totalPoints = activityData.pace_data.length;
  trimStartIndex = Math.floor((startPercent / 100) * (totalPoints - 1));
  trimEndIndex = Math.floor((endPercent / 100) * (totalPoints - 1));

  // Make sure indices are valid
  trimStartIndex = Math.max(0, Math.min(totalPoints - 1, trimStartIndex));
  trimEndIndex = Math.max(0, Math.min(totalPoints - 1, trimEndIndex));

  // Update chart highlighting
  if (paceChart.options.plugins.annotation) {
    // Remove existing annotation
    paceChart.options.plugins.annotation.annotations = {};
  } else {
    // Initialize annotation plugin
    paceChart.options.plugins.annotation = {
      annotations: {},
    };
  }

  // Add box annotation for the trimmed section
  paceChart.options.plugins.annotation.annotations.trimBox = {
    type: "box",
    xMin: activityData.pace_data[trimStartIndex].minutes,
    xMax: activityData.pace_data[trimEndIndex].minutes,
    backgroundColor: "rgba(0, 128, 0, 0.1)",
    borderColor: "rgba(0, 128, 0, 0.5)",
    borderWidth: 1,
  };

  // Update the chart
  paceChart.update();
}

/**
 * Update metrics based on the trimmed section
 */
function updateTrimmedMetrics() {
  if (!activityData || !activityData.pace_data) return;

  const totalPoints = activityData.pace_data.length;
  if (totalPoints === 0) return;

  // Save original metrics
  if (originalMetrics.distance === 0) {
    originalMetrics.distance = activityData.activity.distance;
    originalMetrics.time = activityData.activity.elapsed_time;

    // Calculate original pace (seconds per meter)
    if (originalMetrics.distance > 0 && originalMetrics.time > 0) {
      originalMetrics.pace = originalMetrics.time / originalMetrics.distance;
    }
  }

  // Calculate trimmed metrics
  const trimmedData = activityData.pace_data.slice(
    trimStartIndex,
    trimEndIndex + 1
  );

  if (trimmedData.length > 0) {
    // Get distance from trimmed data
    const lastPoint = trimmedData[trimmedData.length - 1];
    const firstPoint = trimmedData[0];

    // Calculate trimmed distance and time
    const trimmedDistance = lastPoint.distance - firstPoint.distance;
    const trimmedTime = lastPoint.time - firstPoint.time;

    // If editing distance is checked, use that value instead
    const editDistanceCheckbox = document.getElementById(
      "editDistanceCheckbox"
    );
    if (editDistanceCheckbox && editDistanceCheckbox.checked) {
      const newDistanceInput = document.getElementById("newDistance");
      const newDistanceValue = parseFloat(newDistanceInput.value);

      if (!isNaN(newDistanceValue) && newDistanceValue > 0) {
        // Convert miles to meters
        const isMetric = activityData.activity.is_metric;
        const newDistanceMeters = isMetric
          ? newDistanceValue * 1000 // km to m
          : newDistanceValue * 1609.34; // miles to m

        editedMetrics.distance = newDistanceMeters;
      } else {
        editedMetrics.distance = trimmedDistance;
      }
    } else {
      editedMetrics.distance = trimmedDistance;
    }

    editedMetrics.time = trimmedTime;

    // Calculate pace (seconds per meter)
    if (editedMetrics.distance > 0 && editedMetrics.time > 0) {
      editedMetrics.pace = editedMetrics.time / editedMetrics.distance;
    }

    // Update the comparison table
    updateComparisonTable();
  }
}

/**
 * Load activity data for visualization
 */
async function loadActivityVisualization(activityId) {
  // Show loading state
  const visualizationContainer = document.getElementById(
    "activityVisualization"
  );
  visualizationContainer.innerHTML =
    '<div class="loading-spinner"></div><p class="loading-text">Loading activity data...</p>';
  visualizationContainer.style.display = "block";

  try {
    // Get token from localStorage
    const token = getStoredToken();

    if (!token) {
      showMessage(
        "Authentication required. Please log in with Strava.",
        "error"
      );
      showAuthSection();
      return;
    }

    // Build URL with parameters
    const url = `${BACKEND_URL}/activity-streams?activity_id=${activityId}&token=${encodeURIComponent(
      token
    )}`;

    // Make the request
    const response = await fetch(url);

    if (!response.ok) {
      throw new Error(`Failed to load activity data (${response.status})`);
    }

    // Parse the response
    activityData = await response.json();

    if (activityData.error) {
      throw new Error(activityData.error);
    }

    // Restore visualization container content
    visualizationContainer.innerHTML = `
            <h3>Activity Insights</h3>
            
            <!-- Pace/Speed Graph -->
            <div class="graph-container">
                <div class="graph-header">
                    <h4>Pace Over Time</h4>
                    <div class="graph-controls">
                        <button id="toggleSpeedPace" class="toggle-button">
                            <span class="toggle-option active" data-option="pace">Pace</span>
                            <span class="toggle-option" data-option="speed">Speed</span>
                        </button>
                    </div>
                </div>
                <div class="canvas-container">
                    <canvas id="paceChart"></canvas>
                    <div id="trimMarkers" class="trim-markers">
                        <div id="startMarker" class="trim-marker start-marker" title="Trim start point"></div>
                        <div id="endMarker" class="trim-marker end-marker" title="Trim end point"></div>
                    </div>
                </div>
                <div class="graph-legend">
                    <div class="legend-item">
                        <span class="legend-color" style="background-color: rgba(252, 76, 2, 0.7);"></span>
                        <span class="legend-label">Original Activity</span>
                    </div>
                    <div class="legend-item">
                        <span class="legend-color" style="background-color: rgba(0, 128, 0, 0.7);"></span>
                        <span class="legend-label">Trimmed Section</span>
                    </div>
                    <div class="legend-item trim-markers-legend">
                        <span class="legend-marker"></span>
                        <span class="legend-label">Trim Points (drag to adjust)</span>
                    </div>
                </div>
            </div>
            
            <!-- Before vs After Comparison -->
            <div class="comparison-container">
                <h4>Before vs After Comparison</h4>
                <div class="comparison-table">
                    <div class="comparison-header">
                        <div class="metric-label"></div>
                        <div class="original-value">Original</div>
                        <div class="edited-value">Edited</div>
                        <div class="difference">Difference</div>
                    </div>
                    <div class="comparison-row">
                        <div class="metric-label">Distance</div>
                        <div id="originalDistance" class="original-value">--</div>
                        <div id="editedDistance" class="edited-value">--</div>
                        <div id="distanceDiff" class="difference">--</div>
                    </div>
                    <div class="comparison-row">
                        <div class="metric-label">Time</div>
                        <div id="originalTime" class="original-value">--</div>
                        <div id="editedTime" class="edited-value">--</div>
                        <div id="timeDiff" class="difference">--</div>
                    </div>
                    <div class="comparison-row">
                        <div class="metric-label">Pace</div>
                        <div id="originalPace" class="original-value">--</div>
                        <div id="editedPace" class="edited-value">--</div>
                        <div id="paceDiff" class="difference">--</div>
                    </div>
                </div>
            </div>
        `;

    // Create the pace chart
    createPaceChart();

    // Initialize marker dragging
    initMarkerDrag();

    // Add toggle event listener
    document
      .getElementById("toggleSpeedPace")
      .addEventListener("click", togglePaceSpeedView);

    // Add distance input event listener to update metrics
    const newDistanceInput = document.getElementById("newDistance");
    if (newDistanceInput) {
      newDistanceInput.addEventListener("input", updateTrimmedMetrics);
    }

    const editDistanceCheckbox = document.getElementById(
      "editDistanceCheckbox"
    );
    if (editDistanceCheckbox) {
      editDistanceCheckbox.addEventListener("change", updateTrimmedMetrics);
    }
  } catch (error) {
    console.error("Error loading activity visualization:", error);
    visualizationContainer.innerHTML = `
            <div class="error-message">
                <i class="fas fa-exclamation-circle"></i>
                <p>Failed to load activity data: ${error.message}</p>
            </div>
        `;
  }
}

// Extend the existing fetchActivities function to add event handlers for activity selection
const originalFetchActivities = fetchActivities;
fetchActivities = async function () {
  await originalFetchActivities();

  // We no longer need to add event handlers here because we're adding them directly
  // in the renderActivities function, but we'll leave this as a backup
  const radioButtons = document.querySelectorAll(
    'input[name="selectedActivity"]'
  );
  radioButtons.forEach((radio) => {
    radio.addEventListener("change", function () {
      if (this.checked) {
        const activityId = this.value;
        const activityDistance = this.getAttribute("data-distance");
        selectActivity(activityId, activityDistance);
      }
    });
  });
};

// Theme management functions
function setTheme(themeName) {
  localStorage.setItem("theme", themeName);
  document.documentElement.setAttribute("data-theme", themeName);
}

function toggleTheme() {
  const currentTheme = localStorage.getItem("theme") || "light";
  const newTheme = currentTheme === "light" ? "dark" : "light";
  setTheme(newTheme);
  updateThemeToggleIcon();
}

function updateThemeToggleIcon() {
  const themeToggle = document.querySelector(".theme-toggle i");
  if (!themeToggle) return;

  const currentTheme = localStorage.getItem("theme") || "light";
  themeToggle.className =
    currentTheme === "light" ? "fas fa-moon" : "fas fa-sun";
}

function initTheme() {
  // Check for saved theme preference or use system preference
  const savedTheme = localStorage.getItem("theme");

  if (savedTheme) {
    setTheme(savedTheme);
  } else {
    // Check if system prefers dark mode
    if (
      window.matchMedia &&
      window.matchMedia("(prefers-color-scheme: dark)").matches
    ) {
      setTheme("dark");
    } else {
      setTheme("light");
    }
  }

  // Add theme toggle button if it doesn't exist
  if (!document.querySelector(".theme-toggle")) {
    const themeToggle = document.createElement("button");
    themeToggle.className = "theme-toggle";
    themeToggle.innerHTML = '<i class="fas fa-moon"></i>'; // Default icon
    themeToggle.addEventListener("click", toggleTheme);
    document.body.appendChild(themeToggle);

    // Update the icon based on current theme
    updateThemeToggleIcon();
  }
}

// Initialize theme on document load
document.addEventListener("DOMContentLoaded", function () {
  initTheme();

  // ... existing code ...
});
