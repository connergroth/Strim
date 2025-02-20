import { useState } from "react";

export default function FileUploader() {
  const [selectedFile, setSelectedFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState("");

  const handleFileChange = (event) => {
    setSelectedFile(event.target.files[0]);
  };

  const handleUpload = async () => {
    if (!selectedFile) {
      setMessage("Please select a file to upload.");
      return;
    }

    setUploading(true);
    setMessage("");
    const formData = new FormData();
    formData.append("file", selectedFile);

    try {
      const response = await fetch("http://localhost:5000/upload", {
        method: "POST",
        body: formData,
      });

      const result = await response.json();
      if (response.ok) {
        setMessage("File uploaded successfully!");
      } else {
        setMessage("Upload failed: " + result.error);
      }
    } catch (error) {
      setMessage("Error uploading file.");
    }

    setUploading(false);
  };

  return (
    <div className="flex flex-col items-center p-4 border rounded-lg shadow-md max-w-md mx-auto mt-10 bg-[#FC4C02] text-white">
      <img src="/strava-trimmer-logo.png" alt="Strava Trimmer Logo" className="w-24 h-24 mb-4" />
      <h2 className="text-xl font-semibold mb-4">Upload Your FIT File</h2>
      <input type="file" accept=".fit" onChange={handleFileChange} className="mb-4 text-black" />
      {selectedFile && <p className="text-gray-200">Selected: {selectedFile.name}</p>}
      <button
        onClick={handleUpload}
        disabled={uploading}
        className="mt-3 px-4 py-2 bg-white text-[#FC4C02] rounded-lg disabled:bg-gray-300"
      >
        {uploading ? "Uploading..." : "Upload"}
      </button>
      {message && <p className="mt-2 text-sm text-gray-200">{message}</p>}
    </div>
  );
}
