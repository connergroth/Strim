document.addEventListener("DOMContentLoaded", function () {
    const uploadButton = document.getElementById("uploadButton");
    uploadButton.addEventListener("click", uploadFile);
});

function uploadFile() {
    const fileInput = document.getElementById("fileInput");
    const message = document.getElementById("message");

    if (!fileInput.files.length) {
        message.textContent = "Please select a file to upload.";
        return;
    }

    const file = fileInput.files[0];
    const formData = new FormData();
    formData.append("file", file);

    message.textContent = "Uploading...";

    fetch("http://localhost:5000/upload", {
        method: "POST",
        body: formData
    })
    .then(response => response.json())
    .then(result => {
        if (result.error) {
            message.textContent = "Upload failed: " + result.error;
        } else {
            message.textContent = "File uploaded successfully!";
        }
    })
    .catch(() => {
        message.textContent = "Error uploading file.";
    });
}
