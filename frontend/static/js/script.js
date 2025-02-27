const BACKEND_URL = "https://strim-production.up.railway.app";

function checkAuthStatus() {
    const stravaToken = localStorage.getItem("strava_token");

    if (!stravaToken) {
        console.log("❌ User is NOT authenticated. Redirecting to login...");
        if (!window.location.pathname.includes("index.html")) {
            window.location.href = "/index.html";
        }
    }
    return;
}

async function fetchActivities() {
    try {
        console.log("Fetching activities...");

        const response = await fetch("https://strim-production.up.railway.app/get-activities", {
            method: "GET",
            credentials: "include",  // Ensures cookies are sent
            headers: {
                "Content-Type": "application/json"
            }
        });

        if (!response.ok) {
            console.error(`❌ Error fetching activities: ${response.status} ${response.statusText}`);

            if (response.status === 401) {
                alert("Session expired. Please log in again.");
                localStorage.removeItem("strava_token");  // Clear invalid token
                window.location.href = "/index.html";  // Redirect to login
            }
            return;
        }

        const data = await response.json();
        console.log("✅ Fetched activities:", data);

        if (!data.activities) {
            document.getElementById("activityList").innerHTML = "<tr><td colspan='4'>No activities found</td></tr>";
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
        alert("Failed to load activities. Please try again.");
    }
}

function toggleDistanceInput() {
    const editDistanceChecked = document.getElementById("editDistanceCheckbox").checked;
    document.getElementById("distanceInputContainer").style.display = editDistanceChecked ? "block" : "none";
}

async function downloadAndProcessActivity() {
    const selectedActivity = document.querySelector('input[name="selectedActivity"]:checked');
    if (!selectedActivity) {
        alert("Please select an activity.");
        return;
    }

    const activityId = selectedActivity.value;
    localStorage.setItem("selectedActivityId", activityId);

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
        const url = `/download-fit?activity_id=${activityId}&edit_distance=${editDistance}&new_distance=${encodedDistance}`;

        const response = await fetch(url);
        const result = await response.json();

        if (result.success) {
            document.getElementById("message").innerText = "Upload complete! Redirecting to Strava...";
            window.location.href = `https://www.strava.com/activities/${result.new_activity_id}`;
        } else {
            alert("Error: " + result.error);
        }
    } catch (error) {
        console.error("Error processing activity:", error);
        alert("An error occurred while processing the activity.");
    }
}

async function handleStravaOAuth() {
    const urlParams = new URLSearchParams(window.location.search);
    const code = urlParams.get("code");

    if (!code) {
        console.warn("No auth code found in URL. Checking if already logged in...");

        const stravaToken = localStorage.getItem("strava_token");
        if (stravaToken) {
            console.log("✅ User already authenticated. Showing activity selection...");
            document.getElementById("authSection").classList.add("hidden");
            document.getElementById("activitySection").classList.remove("hidden");
            fetchActivities();
            return;
        }

        console.error("User is not authenticated. Redirecting to login.");
        return;
    }

    console.log("Received OAuth code:", code);

    try {
        const response = await fetch(`${BACKEND_URL}/auth/callback`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ code })
        });

        const data = await response.json();
        if (data.access_token) {
            console.log("✅ Authentication successful:", data);
            localStorage.setItem("strava_token", data.access_token);

            // Remove the auth code from URL to prevent unwanted refresh behavior
            window.history.replaceState({}, document.title, "/");

            document.getElementById("authSection").classList.add("hidden");
            document.getElementById("activitySection").classList.remove("hidden");
            fetchActivities();
        } else {
            console.error("OAuth failed", data);
            alert("Authentication failed. Please try again.");
            window.location.href = "/index.html"; 
        }
    } catch (error) {
        console.error("Error during OAuth process:", error);
        alert("An error occurred. Please try logging in again.");
        window.location.href = "/index.html";
    }
}

function logout() {
    console.log("🔴 Logging out...");
    localStorage.removeItem("strava_token");  // Remove the stored token

    // Redirect to login page
    window.location.href = "/index.html";
}

document.addEventListener("DOMContentLoaded", function () {
    const urlParams = new URLSearchParams(window.location.search);
    const authCode = urlParams.get("code");

    if (authCode) {
        console.log("🔑 OAuth Code Found:", authCode);

        // Save code in localStorage before it's removed
        localStorage.setItem("strava_auth_code", authCode);

        // Remove code from URL without reloading
        window.history.replaceState({}, document.title, window.location.pathname);

        // Redirect to backend (avoid Meta Pixel issues)
        window.location.href = `https://strim-production.up.railway.app/auth/callback?code=${authCode}`;
    } else {
        console.log("❌ No auth code found in URL.");
    }
});
