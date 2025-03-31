// Configuration settings for the application
const config = {
    // Production URLs
    production: {
        backendURL: 'https://strim-production.up.railway.app',
        frontendURL: 'https://strimrun.vercel.app'
    },
    
    // Local development URLs
    development: {
        backendURL: 'http://localhost:8080',
        frontendURL: 'http://localhost:3000'
    },
    
    // Determine environment based on hostname
    getEnvironment() {
        // Check if we're on the production domain
        if (window.location.hostname === 'strimrun.vercel.app' || 
            window.location.hostname === 'strim-conner-groths-projects.vercel.app') {
            return 'production';
        }
        return 'development';
    },
    
    // Get the appropriate backend URL based on environment
    getBackendURL() {
        return this[this.getEnvironment()].backendURL;
    },
    
    // Get the appropriate frontend URL based on environment
    getFrontendURL() {
        return this[this.getEnvironment()].frontendURL;
    }
};

export default config;