import platform

import requests

import y_web.pyinstaller_utils.installation_id as installation_id


def check_for_updates():
    """
    Check for the latest release of YSocial and compare it with the current version.

    Returns:
        dict: Information about the latest release and download links for different platforms.
    """

    current_version = installation_id.get_version()
    if current_version is None:
        return None

    else:
        current_version = current_version.strip("v")

    latest_release = __get_latest_release()
    if latest_release is None:
        return None

    latest_tag = latest_release["tag"].strip("v")

    if version_tuple(latest_tag) > version_tuple(current_version):
        os = __get_os()
        url, published, size, sha = __get_release_link_by_platform(latest_release, os)

        return {
            "latest_version": latest_tag,
            "release_name": latest_release["name"],
            "published_at": latest_release["published_at"],
            "download": url,
            "size": size,
            "sha256": sha,
        }
    else:
        return None


def __get_os():
    name = platform.system()
    if name == "Darwin":
        return "macos"
    elif name == "Windows":
        return "windows"
    elif name == "Linux":
        return "linux"
    return "unknown"


def version_tuple(v):
    return tuple(map(int, v.split(".")))


def __get_latest_release():
    """
    Fetch the latest release information from the YSocial GitHub repository.

    Returns:
        dict: Release information (tag, name, assets, etc.) or None if not found.
    """
    url = f"https://api.github.com/repos/YSocialTwin/YSocial/releases/latest"
    response = requests.get(url, headers={"Accept": "application/vnd.github+json"})

    if response.status_code == 200:
        data = response.json()
        return {
            "tag": data.get("tag_name"),
            "name": data.get("name"),
            "published_at": data.get("published_at"),
        }
    else:
        print(f"Error: {response.status_code} — {response.text}")
        return None


def __get_release_link_by_platform(release_data, platform_keyword):
    """
    Get the download link for a specific platform from the release data.

    Args:
        release_data (dict): Release information containing assets.
        platform_keyword (str): Keyword to identify the platform in asset names.
    Returns:
        str: Download URL for the specified platform or None if not found.
    """

    tag = release_data["tag"].strip("v")
    url = f"https://releases.y-not.social/ysocial/latest/release.json"
    response = requests.get(url, headers={"Accept": "application/json"})
    if response.status_code == 200:
        data = response.json()
        version = data["version"].strip("v")
        published = data["published"]
        files = data["files"]

        if platform_keyword in files and tag == version:
            name = files[platform_keyword]["name"]
            url = f"https://releases.y-not.social/ysocial/latest/{name}"
            return url, published, files["size"], files["sha256"]
        return None

    else:
        return response.status_code


def download_file(url, dest_path, exp_size, exp_sha256):
    """
    Download a file from a URL to a specified destination path.

    Args:
        url (str): URL of the file to download.
        dest_path (str): Local path to save the downloaded file.
    """
    response = requests.get(url, stream=True)
    response.raise_for_status()

    with open(dest_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)

    # check file size and sha256
    import hashlib
    import os

    actual_size = os.path.getsize(dest_path)
    if actual_size != exp_size:
        return False, "File size mismatch"
    sha256_hash = hashlib.sha256()
    with open(dest_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    actual_sha256 = sha256_hash.hexdigest()
    if actual_sha256 != exp_sha256:
        return False, "SHA256 mismatch"
    print(f"Update downloaded successfully")
    return True, "File downloaded and verified successfully."
