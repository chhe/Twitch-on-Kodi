#-*- encoding: utf-8 -*-
VERSION='0.4.0'
MAX_RETRIES=5
import sys
from urllib2 import Request, urlopen, URLError, HTTPError
from itertools import islice, chain, repeat
from xbmcswift2 import Plugin
from urllib import quote_plus

try:
    import json
except:
    import simplejson as json  # @UnresolvedImport

if sys.version_info >= (2, 7, 9):
    import ssl
    ssl._create_default_https_context = ssl._create_unverified_context

PLUGIN = Plugin()

class JSONScraper(object):
    '''
    Encapsulates execution request and parsing of response
    '''
    def __init__(self, logger):
        object.__init__(self)
        self.logger = logger
    '''
        Download Data from an url and returns it as a String
        @param url Url to download from (e.g. http://www.google.com)
        @param headers currently unused, backwards compability
        @returns String of data from URL
    '''
    def downloadWebData(self, url, headers=None):
        data = ""
        for _ in range(MAX_RETRIES):
            try:
                req = Request(url)
                req.add_header(Keys.USER_AGENT, Keys.USER_AGENT_STRING)
                if headers:
                    for key, value in headers.iteritems():
                        req.add_header(key, value)
                response = urlopen(req)
                if sys.version_info < (3, 0):
                    data = response.read().decode('utf-8')
                else:
                    data = response.readall().decode('utf-8')
                response.close()
                break
            except Exception as err:
                if not isinstance(err, HTTPError):
                    self.logger.debug("Error %s during HTTP Request, abort", repr(err))
                    raise # propagate non-HTTPError
                self.logger.debug("HTTP-Error during HTTP Request, return code: %s", repr(err.code))
                if (err.code == 403):
                    raise TwitchException(TwitchException.ACCESS_FORBIDDEN)
        else:
            raise TwitchException(TwitchException.HTTP_ERROR)
        return data

    '''
        Download Data from an url and returns it as JSON
        @param url Url to download from
        @param headers currently unused, backwards compability
        @returns JSON Object with data from URL
    '''
    def getJson(self, url, headers=None):
        def getClientID():
            client_id = PLUGIN.get_setting('oauth_client_id')
            if not client_id:
                try:
                    client_id = b64decode(Keys.CLIENT_ID)
                except:
                    client_id = ''
            return client_id

        if not headers:
            headers = {}
        headers.setdefault(Keys.CLIENT_ID_HEADER, getClientID())

        jsonString = self.downloadWebData(url, headers)
        try:
            jsonDict = json.loads(jsonString)
            self.logger.debug(json.dumps(jsonDict, indent=4, sort_keys=True))
            return jsonDict
        except:
            raise TwitchException(TwitchException.JSON_ERROR)

class M3UPlaylist(object):
    def __init__(self, input, qualityList = None):
        self.playlist = dict()

        def parseQuality(ExtXMediaLine,ExtXStreamInfLine,Url):
            #find name of current quality, NAME=", 6 chars
            namePosition = ExtXMediaLine.find('NAME')
            if(namePosition==-1):
                raise TwitchException()
            qualityString = ''
            namePosition+=6
            for char in ExtXMediaLine[namePosition:]:
                if(char=='"'):
                    break
                qualityString += char
            return qualityString, Url

        lines = input.splitlines()
        linesIterator = iter(lines)
        for line in linesIterator:
            if(line.startswith('#EXT-X-MEDIA')):
                quality, url = parseQuality(line, next(linesIterator), next(linesIterator))
                self.playlist[quality] = url
        if not self.playlist:
            #playlist dict is empty
            raise ValueError('could not find playable urls')

    def getQualities(self):
        sortedQualities = list(self.playlist.keys())
        sortedQualities.sort(key=lambda item: Keys.SORTED_QUALITY_LIST.index(item) if item in Keys.SORTED_QUALITY_LIST else sys.maxint)
        return sortedQualities

    #returns selected quality or best match if not available
    def getQuality(self, selectedQuality):
        if(selectedQuality in self.playlist.keys()):
            #selected quality is available
            return self.playlist[selectedQuality]
        else:
            return self.playlist.itervalues().next()

    def __str__(self):
        return repr(self.playlist)

class TwitchTV(object):
    '''
    Uses Twitch API to fetch json-encoded objects
    every method returns a dict containing the objects\' values
    '''
    def __init__(self, logger):
        self.logger = logger
        self.scraper = JSONScraper(logger)

    def getFeaturedStream(self):
        url = ''.join([Urls.STREAMS, Keys.FEATURED])
        return self._fetchItems(url, Keys.FEATURED)

    def getGames(self, offset=0, limit=10):
        options = Urls.OPTIONS_OFFSET_LIMIT.format(offset, limit)
        url = ''.join([Urls.GAMES, Keys.TOP, options])
        return self._fetchItems(url, Keys.TOP)

    def getChannels(self, offset=0, limit=10):
        options = Urls.OPTIONS_OFFSET_LIMIT.format(offset, limit)
        url = ''.join([Urls.STREAMS, options])
        return self._fetchItems(url, Keys.STREAMS)

    def getGameStreams(self, gameName, offset=0, limit=10):
        quotedName = quote_plus(gameName)
        options = Urls.OPTIONS_OFFSET_LIMIT_GAME.format(offset, limit, quotedName)
        url = ''.join([Urls.BASE, Keys.STREAMS, options])
        return self._fetchItems(url, Keys.STREAMS)

    def searchStreams(self, query, offset=0, limit=10):
        quotedQuery = quote_plus(query)
        options = Urls.OPTIONS_OFFSET_LIMIT_QUERY.format(offset, limit, quotedQuery)
        url = ''.join([Urls.SEARCH, Keys.STREAMS, options])
        return self._fetchItems(url, Keys.STREAMS)

    def getFollowingStreams(self, username):
        #Get ChannelNames
        followingChannels = self.getFollowingChannelNames(username)
        channelNames = self._filterChannelNames(followingChannels)

        limit = 100

        #get Streams of that Channels
        baseUrl = ''.join([Urls.BASE, Keys.STREAMS])
        chunks = self._chunk([channels[Keys.NAME] for channels in channelNames], limit)

        liveChannels = []

        for chunk in chunks:
            options = '?channel=' + ','.join(chunk) + '&limit=' + str(limit)
            url = baseUrl + options
            liveChannels = liveChannels + self._fetchItems(url, Keys.STREAMS)

        liveChannels.sort(key=lambda item: item['viewers'], reverse=True)

        channels = {'live' : liveChannels}
        channels['others'] = channelNames
        return channels

    def getFollowingGames(self, username):
        acc = []
        limit = 100
        offset = 0
        quotedUsername = quote_plus(username)
        baseurl = Urls.FOLLOWED_GAMES.format(quotedUsername)
        while True:
            url = baseurl + Urls.OPTIONS_OFFSET_LIMIT.format(offset, limit)
            temp = self._fetchItems(url, Keys.FOLLOWS)
            if (len(temp) == 0):
                break;
            acc = acc + temp
            offset = offset + limit
        return acc

    def getFollowerVideos(self, username, offset, limit, broadcast_type):
        url = Urls.CHANNEL_VIDEOS.format(username, limit, offset, broadcast_type)
        items = self.scraper.getJson(url)
        return {Keys.TOTAL : items[Keys.TOTAL], Keys.VIDEOS : items[Keys.VIDEOS]}

    def getVideoTitle(self, id, oAuthToken):
        url = Urls.VIDEO_INFO.format(id)  + '?oauth_token=' + oAuthToken
        return self._fetchItems(url, 'title')

    def __getChunkedVideo(self, id, oAuthToken):
        # twitch site queries chunked playlists also with token
        # not necessary yet but might change (similar to vod playlists)
        url = Urls.VIDEO_PLAYLIST.format(id)
        return self.scraper.getJson(url)

    def __getVideoPlaylistChunkedArchived(self, id, oAuthToken):
        vidChunks = self.__getChunkedVideo(id, oAuthToken)
        chunks = []
        chunks = vidChunks['chunks']['live']

        title = self.getVideoTitle(id)
        itemTitle = '%s - Part {0} of %s' % (title, len(chunks))

        playlist = [('', ('', vidChunks['preview']))]
        curN = 0
        for chunk in chunks:
            curN += 1
            playlist += [(chunk['url'], (itemTitle.format(curN), vidChunks['preview']))]

        return playlist

    def _getVideoVodPlaylist(self, id, oAuthToken):
        vodid = id[1:]
        url = Urls.VOD_TOKEN.format(vodid) + '?oauth_token=' + oAuthToken
        access_token = self.scraper.getJson(url)

        playlistQualitiesUrl = Urls.VOD_PLAYLIST.format(
            vodid,
            access_token['token'],
            access_token['sig'])
        playlistQualitiesData = self.scraper.downloadWebData(playlistQualitiesUrl)
        try:
            playlistQualities = M3UPlaylist(playlistQualitiesData)
            return playlistQualities
        except ValueError:
            raise TwitchException(TwitchException.PLAYLIST_ERROR)

    def getQualitiesForVideo(self, videoId, oAuthToken):
        videoPlaylist = self._getVideoVodPlaylist(videoId, oAuthToken)
        return videoPlaylist.getQualities()

    def getVideoVodUrl(self, videoId, maxQuality, oAuthToken):
        videoPlaylist = self._getVideoVodPlaylist(videoId, oAuthToken)
        vodUrl = videoPlaylist.getQuality(maxQuality)

        return vodUrl

    def getVideoPlaylist(self, id, oAuthToken):
        playlist = self.__getVideoPlaylistChunkedArchived(id, oAuthToken)
        return playlist

    def getFollowingChannelNames(self, username):
        acc = []
        limit = 100
        offset = 0
        quotedUsername = quote_plus(username)
        baseurl = Urls.FOLLOWED_CHANNELS.format(quotedUsername)
        while True:
            url = baseurl + Urls.OPTIONS_OFFSET_LIMIT.format(offset, limit)
            temp = self._fetchItems(url, Keys.FOLLOWS)
            if (len(temp) == 0):
                break;
            acc = acc + temp
            offset = offset + limit
        return acc

    def _getStreamPlaylist(self, channelName):
        #Get Access Token (not necessary at the moment but could come into effect at any time)
        tokenurl= Urls.CHANNEL_TOKEN.format(channelName)
        channeldata = self.scraper.getJson(tokenurl)
        channeltoken= channeldata['token']
        channelsig= channeldata['sig']

        #Download and Parse Multiple Quality Stream Playlist
        try:
            hls_url = Urls.HLS_PLAYLIST.format(channelName,channelsig,channeltoken)
            data = self.scraper.downloadWebData(hls_url)
            playlist = M3UPlaylist(data)
            return playlist

        except TwitchException:
            #HTTP Error in download web data -> stream is offline
            raise TwitchException(TwitchException.STREAM_OFFLINE)
        except ValueError:
            raise TwitchException(TwitchException.PLAYLIST_ERROR)

    def getQualitiesForStream(self, channelName):
        streamPlaylist = self._getStreamPlaylist(channelName)
        return streamPlaylist.getQualities()

    #gets playable livestream url
    def getLiveStream(self, channelName, maxQuality):
        streamPlaylist = self._getStreamPlaylist(channelName)
        return streamPlaylist.getQuality(maxQuality)

    def _filterChannelNames(self, channels):
        tmp = [{Keys.DISPLAY_NAME : item[Keys.CHANNEL][Keys.DISPLAY_NAME], Keys.NAME : item[Keys.CHANNEL][Keys.NAME], Keys.LOGO : item[Keys.CHANNEL][Keys.LOGO]} for item in channels]
        return sorted(tmp, key=lambda k: k[Keys.DISPLAY_NAME].lower())

    def _fetchItems(self, url, key):
        items = self.scraper.getJson(url)
        return items[key] if items else []

    def _chunk(self, it, size):
        it = iter(it)
        return iter(lambda: tuple(islice(it, size)), ())

class Keys(object):
    '''
    Should not be instantiated, just used to categorize
    string-constants
    '''

    BITRATE = 'bitrate'
    CHANNEL = 'channel'
    CHANNELS = 'channels'
    CONNECT = 'connect'
    BACKGROUND = 'background'
    DISPLAY_NAME = 'display_name'
    FEATURED = 'featured'
    FOLLOWS = 'follows'
    GAME = 'game'
    LOGO = 'logo'
    BOX = 'box'
    LARGE = 'large'
    MEDIUM = 'medium'
    NAME = 'name'
    NEEDED_INFO = 'needed_info'
    PLAY = 'play'
    PLAYPATH = 'playpath'
    QUALITY = 'quality'
    RTMP = 'rtmp'
    STREAMS = 'streams'
    REFERER = 'Referer'
    RTMP_URL = 'rtmpUrl'
    STATUS = 'status'
    STREAM = 'stream'
    SWF_URL = 'swfUrl'
    TOKEN = 'token'
    TOP = 'top'
    TOTAL = '_total'
    USER_AGENT = 'User-Agent'
    USER_AGENT_STRING = 'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:6.0) Gecko/20100101 Firefox/6.0'
    VIDEOS = 'videos'
    VIDEO_BANNER = 'video_banner'
    VIDEO_HEIGHT = 'video_height'
    VIEWERS = 'viewers'
    PREVIEW = 'preview'
    TITLE = 'title'
    LENGTH = 'length'

    CLIENT_ID_HEADER = 'Client-ID'
    CLIENT_ID = ''

    DESCRIPTION = 'description'
    CREATED_AT = 'created_at'
    TITLE = 'title'
    VIEWS = 'views'

    LIVE_PREVIEW_IMAGES = '%://static-cdn.jtvnw.net/previews-ttv/live_user_%-%___x%___.%'

    SORTED_QUALITY_LIST = [
                            'Source',
                            'live',
                            '1080p60 - source',
                            '1080p60',
                            '1080p',
                            '720p60 - source',
                            '720p60',
                            '720p30 - source',
                            '720p30',
                            '720p',
                            'High',
                            '540p30',
                            '540p',
                            'Medium',
                            '480p30',
                            '480p',
                            'Low',
                            '360p30',
                            '360p',
                            '240p30',
                            '240p',
                            'Mobile',
                            '144p30',
                            '144p'
                          ]


class Urls(object):
    '''
    Should not be instantiated, just used to categorize
    string-constants
    '''
    BASE = 'https://api.twitch.tv/kraken/'
    FOLLOWED_CHANNELS = BASE + 'users/{0}/follows/channels'
    GAMES = BASE + 'games/'
    STREAMS = BASE + 'streams/'
    SEARCH = BASE + 'search/'

    CHANNEL_TOKEN = 'https://api.twitch.tv/api/channels/{0}/access_token'
    VOD_TOKEN = 'https://api.twitch.tv/api/vods/{0}/access_token'

    OPTIONS_OFFSET_LIMIT = '?offset={0}&limit={1}'
    OPTIONS_OFFSET_LIMIT_GAME = OPTIONS_OFFSET_LIMIT + '&game={2}'
    OPTIONS_OFFSET_LIMIT_QUERY = OPTIONS_OFFSET_LIMIT + '&q={2}'

    HLS_PLAYLIST = 'https://usher.twitch.tv/api/channel/hls/{0}.m3u8?sig={1}&token={2}&allow_source=true'
    VOD_PLAYLIST = 'https://usher.twitch.tv/vod/{0}?nauth={1}&nauthsig={2}&allow_source=true'

    CHANNEL_VIDEOS = 'https://api.twitch.tv/kraken/channels/{0}/videos?limit={1}&offset={2}&broadcast_type={3}'
    VIDEO_PLAYLIST = 'https://api.twitch.tv/api/videos/{0}'
    VIDEO_INFO = 'https://api.twitch.tv/kraken/videos/{0}'
    FOLLOWED_GAMES = 'https://api.twitch.tv/api/users/{0}/follows/games'


class TwitchException(Exception):

    NO_STREAM_URL = 0
    STREAM_OFFLINE = 1
    HTTP_ERROR = 2
    JSON_ERROR = 3
    PLAYLIST_ERROR = 4
    ACCESS_FORBIDDEN = 5

    def __init__(self, code):
        Exception.__init__(self)
        self.code = code

    def __str__(self):
        return repr(self.code)
