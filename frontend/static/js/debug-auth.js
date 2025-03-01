// debug-auth.js - Add this as a new file in your static/js directory
// This is a standalone script for debugging auth issues

(function() {
    console.log("🔍 Auth Debugger Starting");
    
    // Constants
    const BACKEND_URL = "https://strim-production.up.railway.app";
    
    // Helper function to display status
    function logStatus(message, type = "info") {
        console.log(`[${type.toUpperCase()}] ${message}`);
        
        // Also display in page if in debug mode
        const urlParams = new URLSearchParams(window.location.search);
        if (urlParams.get("debug") === "true") {
            // Create debug container if it doesn't exist
            let debugContainer = document.getElementById("debug-container");
            if (!debugContainer) {
                debugContainer = document.createElement("div");
                debugContainer.id = "debug-container";
                debugContainer.style.position = "fixed";
                debugContainer.style.bottom = "10px";
                debugContainer.style.right = "10px";
                debugContainer.style.width = "400px";
                debugContainer.style.maxHeight = "400px";
                debugContainer.style.overflow = "auto";
                debugContainer.style.background = "#f9f9f9";
                debugContainer.style.border = "1px solid #ddd";
                debugContainer.style.borderRadius = "4px";
                debugContainer.style.padding = "10px";
                debugContainer.style.zIndex = "9999";
                document.body.appendChild(debugContainer);
            }
            
            // Add message
            const msgEl = document.createElement("div");
            msgEl.style.borderBottom = "1px solid #eee";
            msgEl.style.padding = "4px 0";
            msgEl.style.fontSize = "12px";
            msgEl.style.color = type === "error" ? "red" : type === "success" ? "green" : "black";
            msgEl.textContent = message;
            debugContainer.appendChild(msgEl);
            
            // Scroll to bottom
            debugContainer.scrollTop = debugContainer.scrollHeight;
        }
    }
    
    // Check if cookies are enabled
    function areCookiesEnabled() {
        try {
            document.cookie = "testcookie=1";
            const result = document.cookie.indexOf("testcookie=") !== -1;
            document.cookie = "testcookie=1; expires=Thu, 01 Jan 1970 00:00:00 UTC";
            return result;
        } catch (e) {
            return false;
        }
    }
    
    // Check if running on HTTPS
    function isHttps() {
        return window.location.protocol === "https:";
    }
    
    // Test CORS and cookies
    async function testCors() {
        try {
            logStatus("Testing CORS with ping endpoint...");
            
            const response = await fetch(`${BACKEND_URL}/api/ping`, {
                method: "GET",
                mode: "cors",
                credentials: "include"
            });
            
            if (response.ok) {
                const data = await response.json();
                logStatus(`Ping successful: ${data.message}`, "success");
                return true;
            } else {
                logStatus(`Ping failed with status: ${response.status}`, "error");
                return false;
            }
        } catch (error) {
            logStatus(`CORS test error: ${error.message}`, "error");
            return false;
        }
    }
    
    // Test session status
    async function testSession() {
        try {
            logStatus("Testing session status...");
            
            const response = await fetch(`${BACKEND_URL}/api/session-status`, {
                method: "GET",
                credentials: "include",
                cache: "no-store"
            });
            
            const data = await response.json();
            
            if (data.authenticated) {
                logStatus(`Session is valid. User: ${data.athlete?.firstname || 'Unknown'}`, "success");
                return true;
            } else {
                logStatus(`Session is invalid. Reason: ${data.reason}`, "error");
                return false;
            }
        } catch (error) {
            logStatus(`Session test error: ${error.message}`, "error");
            return false;
        }
    }
    
    // Run all tests
    async function runTests() {
        logStatus("=== Starting Authentication Debug Tests ===");
        
        // Basic environment checks
        logStatus(`Cookies enabled: ${areCookiesEnabled()}`);
        if (!areCookiesEnabled()) {
            logStatus("⚠️ Cookies are disabled! Authentication will not work.", "error");
        }
        
        logStatus(`Using HTTPS: ${isHttps()}`);
        if (!isHttps()) {
            logStatus("⚠️ Not using HTTPS! Cross-domain cookies require HTTPS.", "error");
        }
        
        logStatus(`UserAgent: ${navigator.userAgent}`);
        
        // Network tests
        const corsOk = await testCors();
        if (!corsOk) {
            logStatus("⚠️ CORS test failed. This will prevent authentication.", "error");
        }
        
        const sessionOk = await testSession();
        if (!sessionOk) {
            logStatus("Session is not valid. You'll need to log in.", "info");
            
            // Display the login button if it's not already visible
            const authSection = document.getElementById("authSection");
            if (authSection) {
                authSection.classList.remove("hidden");
            }
        } else {
            logStatus("✅ Authentication looks good!", "success");
        }
        
        logStatus("=== Debug Tests Complete ===");
    }
    
    // Wait for DOM to be ready
    document.addEventListener("DOMContentLoaded", function() {
        // Add a debug button if in debug mode
        const urlParams = new URLSearchParams(window.location.search);
        if (urlParams.get("debug") === "true") {
            const debugButton = document.createElement("button");
            debugButton.textContent = "Run Auth Debug";
            debugButton.style.position = "fixed";
            debugButton.style.top = "10px";
            debugButton.style.right = "10px";
            debugButton.style.zIndex = "9999";
            debugButton.addEventListener("click", runTests);
            document.body.appendChild(debugButton);
            
            // Run tests automatically after 1 second
            setTimeout(runTests, 1000);
        }
    });
    
    // Export functions for console use
    window.authDebug = {
        runTests,
        testCors,
        testSession
    };
    
    logStatus("Auth debugger loaded. Type authDebug.runTests() in console to run tests.");
})();