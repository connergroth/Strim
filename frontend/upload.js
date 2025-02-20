document.addEventListener("DOMContentLoaded", function () {
    const fileInput = document.getElementById("fileInput");
    const uploadButton = document.getElementById("uploadButton");
    const message = document.getElementById("message");

    uploadButton.addEventListener("click", function () {
        if (!fileInput.files.length) {
            message.textContent = "Please select a file to upload.";
            return;
        }

        const file = fileInput.files[0];
        const formData = new FormData();
        formData.append("file", file);

        uploadButton.disabled = true;
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
        })
        .finally(() => {
            uploadButton.disabled = false;
        });
    });
});
