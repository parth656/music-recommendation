from flask import Flask, render_template, session, url_for, g, request, redirect
from flask_session import Session
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import json
import requests
from urllib.parse import quote

app = Flask(__name__)
app.secret_key = "454Group11SecretKey"

#  Client Keys
CLIENT_ID = "a5618cb6512944f884284860712a9b26"
CLIENT_SECRET = "214fd159d780433bbc94d948703f6bd4"
client_credentials_manager = SpotifyClientCredentials(client_id=CLIENT_ID,client_secret=CLIENT_SECRET)
sp = spotipy.Spotify(client_credentials_manager=client_credentials_manager)

# Spotify URLS
SPOTIFY_AUTH_URL = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_API_BASE_URL = "https://api.spotify.com"
API_VERSION = "v1"
SPOTIFY_API_URL = "{}/{}".format(SPOTIFY_API_BASE_URL, API_VERSION)

# Server-side Parameters
CLIENT_SIDE_URL = "http://127.0.0.1"
PORT = 8080
REDIRECT_URI = "{}:{}/callback/q".format(CLIENT_SIDE_URL, PORT)
SCOPE = "user-read-recently-played playlist-modify-public playlist-modify-private"
SHOW_DIALOG_bool = True
SHOW_DIALOG_str = str(SHOW_DIALOG_bool).lower()

# Limit number of songs returned on a recommendation (< 100)
LIMIT = str(5)

# Class to store the user's session data
class CurrentUser:
    def __init__(self, session):
        self.auth_header = session["auth_header"]
        self.display_name = session["display_name"]
        self.playlists = session["playlists"]
        self.history = session["history"]

# Builds string of seed tracks based on listening history
def seed_tracks(seed):
    temp = ""
    for key in seed:
        temp+=str(seed[key]+"&")
    return str(temp[0:-1])

# The initial page on launch (Login Screen)        
@app.route("/")
def login():
    return render_template("login.html")

# Spotify verifies spotify account after user logs in
@app.route("/authenticate")
def authenticate():
    params = {'response_type': 'code',
              'redirect_uri': REDIRECT_URI,
              'scope': SCOPE,
              'client_id': CLIENT_ID}

    query_params = "&".join(["{}={}".format(key, quote(val)) for key, val in params.items()])
    response = "{}/?{}".format(SPOTIFY_AUTH_URL, query_params)
    return redirect(response)

# Once verified, spotify accesses all necessary account information
@app.route("/callback/q")
def callback():
    # Requests refresh and access tokens
    authorization = request.args['code']
    data = {'grant_type': 'authorization_code',
         'code': str(authorization),
         'redirect_uri': REDIRECT_URI,
         'client_id': CLIENT_ID,
         'client_secret': CLIENT_SECRET}
    post_request = requests.post(SPOTIFY_TOKEN_URL,data=data)

    # Tokens are Returned to Application
    response_data = json.loads(post_request.text)
    access_token = response_data["access_token"]

    # Use the access token to access Spotify API
    auth_header = {"Authorization": "Bearer {}".format(access_token)}
    session["auth_header"] = auth_header

    # Get profile data
    user_profile_api_endpoint = "{}/me".format(SPOTIFY_API_URL)
    profile_response = requests.get(user_profile_api_endpoint, headers=auth_header)
    profile_data = json.loads(profile_response.text)

    # Save the session data for future use
    session['display_name'] = profile_data["display_name"]

    # Get user playlist data
    playlist_api_endpoint = "https://api.spotify.com/v1/me/playlists?limit=50"
    playlists_response = requests.get(playlist_api_endpoint, headers=auth_header)
    playlist_data = json.loads(playlists_response.text)
    playlists = [item for item in playlist_data["items"]]
    session['playlists'] = {playlist["name"]:playlist["uri"][17:] for playlist in playlists}

    # Get user listening history
    history_api_endpoint = "https://api.spotify.com/v1/me/player/recently-played?limit=50"
    history_response = requests.get(history_api_endpoint, headers=auth_header)
    history_data = json.loads(history_response.text)
    tracks = [item["track"] for item in history_data["items"]]
    session["history"] = {track["name"]:track["id"] for track in tracks}
        
    return redirect(url_for('feed'))

# First page user sees once logged in
@app.route("/feed")
def feed():
    user = CurrentUser(session)
    session["seed"] = []
    message = "Welcome, " + user.display_name + "!"
    
    # Gets recommendation based on user listening history
    history_rec_api_endpoint = "https://api.spotify.com/v1/recommendations?limit="+LIMIT+"&seed_tracks="+seed_tracks(user.history)
    history_rec_response = requests.get(history_rec_api_endpoint, headers=user.auth_header)
    history_rec_data = json.loads(history_rec_response.text)
    session["history_rec"] = {track["name"]:(track["id"],track["artists"][0]["name"]) for track in history_rec_data["tracks"]}

    # Gets recommendation based on each user playlist
    broken_playlists = []
    recommendations = []
    for key in user.playlists.keys():
        plst_api_endpoint = "https://api.spotify.com/v1/playlists/"+str(user.playlists[key])+"/tracks?limit=100"
        plst_response = requests.get(plst_api_endpoint, headers=user.auth_header)
        plst_data = json.loads(plst_response.text)
        plst = {item["track"]["name"]:item["track"]["id"] for item in plst_data["items"]}
        try:
            plst_rec_api_endpoint = "https://api.spotify.com/v1/recommendations?limit="+LIMIT+"&seed_tracks="+seed_tracks(plst)
            plst_rec_response = requests.get(plst_rec_api_endpoint, headers=user.auth_header)
            plst_rec_data = json.loads(plst_rec_response.text)
            plst_rec = {track["name"]:(track["id"],track["artists"][0]["name"]) for track in plst_rec_data["tracks"]}
            recommendations.append(plst_rec)
        except:
            broken_playlists.append(key)
            continue

    # Formats data to display on Feed page
    display_data = {"Listening History": session["history_rec"]}
    i = 0
    for playlist in user.playlists:
        if playlist not in broken_playlists:
            display_data.update({playlist: recommendations[i]})
            i+=1

    return render_template("feed.html", sorted_array=display_data, txt=message)

# Discover tab
@app.route("/discover", methods=['GET','POST'])
def discover():
    user = CurrentUser(session)
    display_lst = []
    gen_rec = {}
    seed = {}
    no_search_results = ""
    rec_header = ""
    message = "Welcome, " + user.display_name + "!"
    # Sets the parameters equal to the inputs the user entered into the form
    if request.method == 'POST':
        song, genre, popularity, length, acousticness, tempo, danceability, energy, instrumentalness, key, liveness, speechiness, valence = '','','','','','','','','','','','',''
        song_name = request.form["song_name"]
        genre = request.form["genre"]
        if genre:
            genre = "&seed_genres="+genre
        popularity = request.form["popularity"]
        if popularity:
            popularity = "&target_popularity="+str(popularity)
        length = request.form["length"]
        if length:
            length = "&target_duration_ms="+str(int(length)*1000)
        acousticness = request.form["acousticness"]
        if acousticness:
            acousticness = "&target_acousticness="+str(acousticness)
        tempo = request.form["tempo"]
        if tempo:
            tempo = "&target_tempo="+str(tempo)
        danceability = request.form["danceability"]
        if danceability:
            danceability = "&target_danceability="+str(danceability)
        energy = request.form["energy"]
        if energy:
            energy = "&target_energy="+str(energy)
        instrumentalness = request.form["instrumentalness"]
        if instrumentalness:
            instrumentalness = "&target_instrumentalness="+str(instrumentalness)
        key = request.form["key"]
        if key:
            key = "&target_key="+str(key)
        liveness = request.form["liveness"]
        if liveness:
            liveness = "&target_liveness="+str(liveness)
        speechiness = request.form["speechiness"]
        if speechiness:
            speechiness = "&target_speechiness="+str(speechiness)
        loudness = request.form["loudness"]
        if loudness:
            loudness = "&target_loudness="+str(loudness)
        valence = request.form["valence"]
        if valence:
            valence = "&target_valence="+str(valence)
        
        # Properly formats the song name
        for word in song_name.split():
            song += word + "+"
        song = song[:-1]
        # Returns 20 songs that match the search
        search_api_endpoint = "https://api.spotify.com/v1/search?q="+song+"&type=track"
        search_response = requests.get(search_api_endpoint, headers=user.auth_header)
        search_data = json.loads(search_response.text)
        # Checks that the search returned any songs
        if "tracks" in list(search_data.keys()) and search_data["tracks"]["total"] != 0:
            search_results = search_data["tracks"]
            # Adds first search result to seed
            seed.update({search_results["items"][0]["name"]: search_results["items"][0]["id"]})
            seed_track = "&seed_tracks="+search_results["items"][0]["id"]
            # Generates recommendation based on seed track and other seed filters
            filters = genre+popularity+length+acousticness+tempo+danceability+energy+instrumentalness+key+liveness+speechiness+loudness+valence
            gen_rec_api_endpoint = "https://api.spotify.com/v1/recommendations?limit="+LIMIT+seed_track+filters
            gen_rec_response = requests.get(gen_rec_api_endpoint, headers=user.auth_header)
            gen_rec_data = json.loads(gen_rec_response.text)
            # If search returns songs, display the songs
            if "tracks" in list(gen_rec_data.keys()):
                gen_rec = {track["name"]:(track["id"],track["artists"][0]["name"]) for track in gen_rec_data["tracks"]}
                rec_header = "Recommendations For You:"
            # If search returns no songs, tell the user
            else:
                no_search_results = "We could not recommend any tracks based on those criteria."
                gen_rec = {}
        # If search returns no songs, tell the user
        else:
            no_search_results = "We could not recommend any tracks based on those criteria."
            gen_rec = {}
        
    return render_template("discover.html", rec_header=rec_header, error_message=no_search_results, sorted_array=gen_rec, txt=message)

# Logout
@app.route("/logout")
def logout():
    session.clear()
    return render_template("login.html")

if __name__ == "__main__":
    app.run(debug=True, port=PORT)
