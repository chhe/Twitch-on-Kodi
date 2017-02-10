# -*- coding: utf-8 -*-
from twitch import Keys
import xbmcgui, xbmc

class PlaylistConverter(object):
    def convertToXBMCPlaylist(self, InputPlaylist):
        playlist = xbmc.PlayList(xbmc.PLAYLIST_VIDEO)
        playlist.clear()

        for (url, details) in InputPlaylist:
            if(details == ()):
                playlist.add(url)
            else:
                (name, preview) = details
                playlist.add(url, xbmcgui.ListItem(name, thumbnailImage=preview))

        return playlist

class JsonListItemConverter(object):

    def __init__(self, PLUGIN, title_length):
        self.plugin = PLUGIN
        self.titleBuilder = TitleBuilder(PLUGIN, title_length)

    def convertCommunityToListItem(self, community):
        name = community[Keys.NAME].encode('utf-8')
        communityID = community['_id']
        channels = community['channels']
        viewers = community['viewers']
        if not name:
            name = self.plugin.get_string(30071)

        try:
            image = community['avatar_image_url']
        except:
            image = 'http://static-cdn.jtvnw.net/ttv-static/404_boxart.jpg'

        name = name + ' (viewers: ' + str(viewers) + ', channels: ' + str(channels) + ')'

        return {'label': name,
                'path': self.plugin.url_for('createListForCommunity',
                                            communityID=communityID, index='0'),
                'icon': image,
                'thumbnail': image
                }

    def convertGameToListItem(self, game):
        name = game[Keys.NAME].encode('utf-8')
        if not name:
            name = self.plugin.get_string(30064)
        try:
            image = game[Keys.BOX].get(Keys.LARGE, '')
        except:
            image = 'http://static-cdn.jtvnw.net/ttv-static/404_boxart.jpg'
        return {'label': name,
                'path': self.plugin.url_for('createListForGame',
                                            gameName=name, index='0'),
                'icon': image,
                'thumbnail': image
                }

    def convertFollowersToListItem(self, follower):
        videobanner = follower.get(Keys.LOGO, '')
        return {'label': follower[Keys.DISPLAY_NAME],
                'path': self.plugin.url_for(endpoint='channelVideos',
                                            name=follower[Keys.NAME]),
                'icon': videobanner,
                'thumbnail': videobanner
                }

    def convertVideoListToListItem(self, video):
        duration = video.get(Keys.LENGTH) if video.get(Keys.LENGTH) else 0
        title = video.get(Keys.TITLE) if video.get(Keys.TITLE) else ''
        description = video.get(Keys.DESCRIPTION) if video.get(Keys.DESCRIPTION) else ''
        date = video.get(Keys.CREATED_AT)[:10] if video.get(Keys.CREATED_AT) else ''
        image = video.get(Keys.PREVIEW) if video.get(Keys.PREVIEW) else ''
        views = video.get(Keys.VIEWS) if video.get(Keys.VIEWS) else ''
        game = video.get(Keys.GAME) if video.get(Keys.GAME) else ''
        channel = video.get(Keys.CHANNEL) if video.get(Keys.CHANNEL) else ''
        channelname = channel.get(Keys.DISPLAY_NAME) if channel.get(Keys.DISPLAY_NAME) else ''
        plot = 'Channel: ' + channelname + '\n' + 'Game: ' + game + '\n' + 'Title: ' + title + '\n' + 'Date: ' + date + '\n' + 'Description: ' + description + '\n' + 'Views: '  + str(views)
        return {'label': title,
                'path': self.plugin.url_for(endpoint='playVideo',
                                            id=video['_id']),
                'is_playable': True,
                'icon': image,
                'thumbnail': image,
                'info': { 'duration': str(duration), 'plot': plot },
                'stream_info': { 'video': { 'duration': duration } }
                }

    def convertStreamToListItem(self, stream):
        channel = stream[Keys.CHANNEL]
        videobanner = channel.get(Keys.VIDEO_BANNER, '')
        preview = stream.get(Keys.PREVIEW, '')
        if preview:
            preview = preview.get(Keys.LARGE, '');
        logo = channel.get(Keys.LOGO, '')
        streamer = channel[Keys.NAME]

        icon = preview if preview else logo
        thumbnail = preview if preview else logo

        contextMenu = [( 'Activity Feed',
                         'Container.Update(%s)' % self.plugin.url_for(
                                endpoint='channelVideos',
                                name=streamer
                         )
                      )]

        return {'label': self.getTitleForStream(stream),
                'path': self.plugin.url_for(endpoint='playLive',
                                            name=streamer),
                'is_playable': True,
                'icon': icon,
                'thumbnail': thumbnail,
                'properties': { 'fanart_image': videobanner },
                'context_menu': contextMenu,
                'info': self.getInfoForStream(stream)
                }

    def getInfoForStream(self, stream):
        titleValues = self.extractStreamTitleValues(stream)
        channel = titleValues.get('streamer') if titleValues.get('streamer') else ''
        game = titleValues.get('game') if titleValues.get('game') else ''
        title = titleValues.get('title') if titleValues.get('title') else ''
        viewers = titleValues.get('viewers') if titleValues.get('viewers') else 0
        return {
                'plot':
                        'Channel: ' + channel + '\n' +
                        'Game: ' + game + '\n' +
                        'Title: ' + title + '\n' +
                        'Viewers: ' + str(viewers),
                'title': title,
                }

    def getTitleForStream(self, stream):
        titleValues = self.extractStreamTitleValues(stream)
        return self.titleBuilder.formatTitle(titleValues)

    def extractStreamTitleValues(self, stream):
        channel = stream[Keys.CHANNEL]

        if Keys.VIEWERS in channel:
            viewers = channel.get(Keys.VIEWERS)
        else:
            viewers = stream.get(Keys.VIEWERS, self.plugin.get_string(30062))

        return {'streamer': channel.get(Keys.DISPLAY_NAME,
                                        self.plugin.get_string(30060)),
                'title': channel.get(Keys.STATUS,
                                     self.plugin.get_string(30061)),
                'game': channel.get(Keys.GAME,
                                     self.plugin.get_string(30064)),
                'viewers': viewers}

class TitleBuilder(object):

    class Templates(object):
        TITLE = u"{title}"
        STREAMER = u"{streamer}"
        STREAMER_TITLE = u"{streamer} - {title}"
        VIEWERS_STREAMER_TITLE = u"{viewers} - {streamer} - {title}"
        STREAMER_GAME_TITLE = u"{streamer} - {game} - {title}"
        GAME_VIEWERS_STREAMER_TITLE = u"[{game}] {viewers} | {streamer} - {title}"
        VIEWERS_STREAMER_GAME_TITLE = u"{viewers} | {streamer} [{game}] {title}"
        ELLIPSIS = u'...'

    def __init__(self, PLUGIN, line_length):
        self.plugin = PLUGIN
        self.line_length = line_length

    def formatTitle(self, titleValues):
        titleSetting = int(self.plugin.get_setting('titledisplay', unicode))
        template = self.getTitleTemplate(titleSetting)

        for key, value in titleValues.iteritems():
            titleValues[key] = self.cleanTitleValue(value)
        title = template.format(**titleValues)

        return self.truncateTitle(title)

    def getTitleTemplate(self, titleSetting):
        options = {0: TitleBuilder.Templates.STREAMER_TITLE,
                   1: TitleBuilder.Templates.VIEWERS_STREAMER_TITLE,
                   2: TitleBuilder.Templates.TITLE,
                   3: TitleBuilder.Templates.STREAMER,
                   4: TitleBuilder.Templates.STREAMER_GAME_TITLE,
                   5: TitleBuilder.Templates.GAME_VIEWERS_STREAMER_TITLE,
                   6: TitleBuilder.Templates.VIEWERS_STREAMER_GAME_TITLE}
        return options.get(titleSetting, TitleBuilder.Templates.STREAMER)

    def cleanTitleValue(self, value):
        if isinstance(value, basestring):
            return unicode(value).replace('\r\n', ' ').strip()
        else:
            return value

    def truncateTitle(self, title):
        truncateSetting = self.plugin.get_setting('titletruncate', unicode)

        if truncateSetting == "true":
            shortTitle = title[:self.line_length]
            ending = (title[self.line_length:] and TitleBuilder.Templates.ELLIPSIS)
            return shortTitle + ending
        return title
