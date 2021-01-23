
import requests
from http.cookiejar import MozillaCookieJar, LoadError
import os
import time


from ..errors import (
    CookieError,
    ParsingError,
    CallbackFunction,
    RetriesExceeded,
    InvalidParameter,
    UnexpectedHTML,
    TimeoutException
)

from ..utils import (
    get_title_of_webpage,
    update_dict_without_overwrite,
    log,
    remove_prefixes,
    pause,
    timed_input
)


from json import JSONDecodeError

from math import ceil
class Timeout():

    # Timeout types
    NORMAL = 0
    INACTIVITY = 1

    _TIMEOUT_MESSAGES = {
        NORMAL: 'Timeout occurred after {} seconds.',
        INACTIVITY: 'No messages received after {}s. Timing out.'
    }

    def __init__(self, timeout, timeout_type=None):
        self.timeout = timeout
        self.reset()

        self.error_message = Timeout._TIMEOUT_MESSAGES.get(
            timeout_type, Timeout._TIMEOUT_MESSAGES[Timeout.NORMAL]).format(self.timeout)

    def reset(self):
        if isinstance(self.timeout, (int, float)):
            self.end_time = time.time() + self.timeout
        else:
            self.end_time = None

    def check_for_timeout(self):
        if self.end_time is not None and time.time() > self.end_time:
            raise TimeoutException(self.error_message)

    def _calculate_remaining(self):
        return self.end_time - time.time()

    def time_until_timeout(self):
        if self.end_time is None:
            return float('inf')
        else:
            return self._calculate_remaining()

    def time_until_timeout_ms(self):
        if self.end_time is None:
            return float('inf')
        else:
            return ceil(self._calculate_remaining()*1000)


class Chat():
    def __init__(self, chat, **kwargs):
        self.chat = chat

        for key in ('title', 'duration', 'is_live', 'start_time'):
            setattr(self, key, kwargs.get(key))
        # self.title = kwargs.get('title')
        # self.duration = kwargs.get('duration')
        # self.is_live = kwargs.get('is_live')
        # self.start_time = kwargs.get('start_time')

        # TODO
        # author/user/uploader/creator

    def __iter__(self):
        for item in self.chat:
            yield item


class ChatDownloader:
    """
    Subclasses of this should redefine the get_chat()
    method and define a _VALID_URL regexp. The
    _DEFAULT_FORMAT field may also be redefined.

    Each chat item is a dictionary and must contain the following fields:

    timestamp:          UNIX time (in microseconds) of when the message was sent.
    message:            Actual content/text of the chat item.
    message_id:         Identifier for the chat item.
    message_type:       Message type of the item.
    author:             A dictionary containing information about the user who
                        sent the message.

                        Mandatory fields:
                        * name      The name of the author.
                        * id        Idenfifier for the author.

                        Optional fields:
                        * display_name  The name of the author which is displayed
                                    to the viewer. This may be different to `name`.
                        * short_name    A shortened version of the author's name.
                        * type      Type of the author.
                        * url       URL for the author's channel/page.

                        * images    A list of the author's profile picture in
                                    different sizes. See below for the
                                    fields which an image may have.
                        * badges    A list of the author's badges.
                                    Mandatory fields:
                                    * title         The title of the badge.

                                    Optional fields:
                                    * id            Identifier for the badge.
                                    * name          Name of the badge.
                                    * version       Version of the badge.
                                    * icon_name     Name of the badge icon.
                                    * icons         A list of images for the badge icons.
                                                    See below for potential fields.
                                    * description   The description of the badge.
                                    * alternative_title
                                                    Alternative title of the badge.
                                    * click_action  Action to perform if the badge is clicked.
                                    * click_url     URL to visit if the badge is clicked.

                        * gender    Gender of the author.

                        The following boolean fields are self-explanatory:
                        * is_banned
                        * is_bot
                        * is_non_coworker
                        * is_original_poster
                        * is_verified


    Mandatory fields for replays/vods/clips (i.e. a video which is not live):

    time_in_seconds:    The number of seconds after the video began, that the message was sent.
    time_text:          Human-readable format for `time_in_seconds`.


    Optional fields:

    sub_message:        Additional text of the message.
    action_type:        Action type of the item.
    amount:             The amount of money which was sent with the message.
    tooltip:            Text to be displayed when hovering over the message.
    icon:               Icon associated with the message.
    target_message_id:  The identifier for a message which this message references.
    action:             The action of the message.
    viewer_is_creator:  Whether the viewer is the creator or not.

    sticker_images:     A list of the sticker image in different sizes. See
                        below for the fields which an image may have.
    sponsor_icons:      A list of the sponsor image in different sizes. See
                        below for potential fields.
    ticker_icons:       A list of the ticker image in different sizes. See
                        below for potential fields.
    ticker_duration:    How long the ticker message is displayed for.


    The following fields indicate HEX colour information for the message:

    author_name_text_colour
    timestamp_colour
    body_background_colour
    header_text_colour
    header_background_colour
    body_text_colour
    background_colour
    money_chip_text_colour
    money_chip_background_colour
    start_background_colour
    amount_text_colour
    end_background_colour
    detail_text_colour


    An image contains the following fields:
    url:                Mandatory. URL of the image.
    id:                 Mandatory. Identifier for the image.
    width:              Width of the image.
    height:             Height of the image.



    TODO
    """

    # id
    # author_id
    # author_name
    # amount
    # message
    # time_text
    # timestamp
    # author_images
    # tooltip
    # icon
    # author_badges
    # badge_icons
    # sticker_images
    # ticker_duration
    # sponsor_icons
    # ticker_icons

    # target_id
    # action
    # viewer_is_creator
    # is_stackable
    # sub_message

    _DEFAULT_INIT_PARAMS = {
        'headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/86.0.4240.111 Safari/537.36',
            'Accept-Language': 'en-US, en'
        },

        'cookies': None,  # cookies file (optional),
        # 'timeout': 10
    }
    _INIT_PARAMS = _DEFAULT_INIT_PARAMS

    _DEFAULT_PARAMS = {
        'url': None,  # should be overridden
        'start_time': None,  # get from beginning (even before stream starts)
        'end_time': None,  # get until end
        # 'callback': None,  # do something for every message


        'max_attempts': 15,  # ~ 2^15s ~ 9 hours
        'retry_timeout': None,  # 1 second
        'timeout': None,


        # TODO timeout between attempts
        'max_messages': None,

        'output': None,

        'logging': 'info',
        'pause_on_debug': False,
        'testing': False, #sets logging->debug, pause_on_debug->True

        # 'safe_print': False,

        # If True, program will not sleep when a timeout instruction is given
        'force_no_timeout': False,

        'force_encoding': None,  # use default


        # stop getting messages after no messages have been sent for `timeout` seconds
        'inactivity_timeout': None,


        'message_groups': ['messages'],  # 'all' can be chosen here
        'message_types': None,  # ['text_message'], # messages



        # Formatting
        'format': None,  # Use default
        'format_file': None,


        # Site specific parameters:
        # [YouTube]
        'chat_type': 'live',  # live or top


        # [Twitch]
        'message_receive_timeout': 0.1, # allows for keyboard interrupts to occur
        'buffer_size': 4096,  # default buffer size for socket,

    }

    _DEFAULT_FORMAT = 'default'

    def __str__(self):
        return ''

    @staticmethod
    def must_add_item(item, message_groups_dict, messages_groups_to_add, messages_types_to_add):
        if 'all' in messages_groups_to_add:  # user wants everything
            return True

        valid_message_types = []
        for message_group in messages_groups_to_add or []:
            valid_message_types += message_groups_dict.get(message_group, [])

        for message_type in messages_types_to_add or []:
            valid_message_types.append(message_type)

        return item.get('message_type') in valid_message_types

    @staticmethod
    def get_param_value(params, key):
        return params.get(key, ChatDownloader._DEFAULT_PARAMS.get(key))

    @staticmethod
    def remap(info, remapping_dict, remapping_functions, remap_key, remap_input, keep_unknown_keys=False, replace_char_with_underscores=None):
        remap = remapping_dict.get(remap_key)

        if remap:
            if isinstance(remap, tuple):
                index, mapping_function = remap
                info[index] = remapping_functions[mapping_function](
                    remap_input)
            else:
                info[remap] = remap_input
        elif keep_unknown_keys:
            if replace_char_with_underscores:
                remap_key = remap_key.replace(
                    replace_char_with_underscores, '_')
            info[remap_key] = remap_input


    def __init__(self, updated_init_params=None):
        """Initialise a new session for making requests."""
        self._INIT_PARAMS.update(updated_init_params or {})

        self.session = requests.Session()
        self.session.headers = self._INIT_PARAMS.get('headers')

        cookies = self._INIT_PARAMS.get('cookies')
        cj = MozillaCookieJar(cookies)

        if cookies:  # is not None
            # Only attempt to load if the cookie file exists.
            if os.path.exists(cookies):
                cj.load(ignore_discard=True, ignore_expires=True)
            else:
                raise CookieError(
                    'The file "{}" could not be found.'.format(cookies))
        self.session.cookies = cj

    def update_session_headers(self, new_headers):
        self.session.headers.update(new_headers)

    def clear_cookies(self):
        self.session.cookies.clear()

    def get_cookies_dict(self):
        return requests.utils.dict_from_cookiejar(self.session.cookies)

    def get_cookie_value(self, name, default=None):
        return self.get_cookies_dict().get(name, default)

    def close(self):
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def _session_post(self, url, **kwargs):
        """Make a request using the current session."""
        return self.session.post(url, **kwargs)

    def _session_get(self, url, **kwargs):
        """Make a request using the current session."""
        return self.session.get(url, **kwargs)

    def _session_get_json(self, url, **kwargs):
        """Make a request using the current session and get json data."""
        s = self._session_get(url, **kwargs)

        try:
            return s.json()
        except JSONDecodeError:
            # print(s.content)
            # TODO determine if html
            webpage_title = get_title_of_webpage(s.text)
            raise UnexpectedHTML(webpage_title, s.text)

    _VALID_URL = None

    def get_chat(self, params):
        raise NotImplementedError

    def get_tests(self):
        t = getattr(self, '_TEST', None)
        if t:
            assert not hasattr(self, '_TESTS'), \
                '%s has _TEST and _TESTS' % type(self).__name__
            tests = [t]
        else:
            tests = getattr(self, '_TESTS', [])
        for t in tests:
            yield t

    # @staticmethod
    # def perform_callback(callback, data, params=None):
    #     if params is None:
    #         params = {}
    #     if callable(callback):
    #         try:
    #             callback(data)
    #         except TypeError:
    #             raise CallbackFunction(
    #                 'Incorrect number of parameters for function '+callback.__name__)
    #     elif callback is None:
    #         pass  # do not perform callback
    #     else:
    #         raise CallbackFunction(
    #             'Unable to call callback function '+callback.__name__)

    # TODO make this a class with a __dict__ attribute

    @staticmethod
    def create_image(url, width=None, height=None, image_id=None):
        if url.startswith('//'):
            url = 'https:' + url
        image = {
            'url':  url,
        }
        if width:
            image['width'] = width
        if height:
            image['height'] = height

        # TODO remove id?
        if width and height and not image_id:
            image['id'] = '{}x{}'.format(width, height)
        elif image_id:
            image['id'] = image_id

        return image

    @staticmethod
    def move_to_dict(info, dict_name, replace_key=None, create_when_empty=False, *info_keys):
        """
        Move all items with keys that contain some text to a separate dictionary.

        These keys are modifed by removing some text.
        """
        if replace_key is None:
            replace_key = dict_name+'_'

        new_dict = {}

        keys = (info_keys or info or {}).copy()
        for key in keys:
            if replace_key in key:
                info_item = info.pop(key, None)
                new_key = key.replace(replace_key, '')

                # set it if it contains info
                if info_item not in (None, [], {}):
                    new_dict[new_key] = info_item

        if dict_name not in info and (create_when_empty or new_dict != {}):
            info[dict_name] = new_dict

        return new_dict

    @staticmethod
    def retry(attempt_number, max_attempts, error, retry_timeout=None, text=None):
        if attempt_number >= max_attempts:
            raise RetriesExceeded(
                'Maximum number of retries has been reached ({}).'.format(max_attempts))

        if text is None:
            text = []
        elif not isinstance(text, (tuple, list)):
            text = [text]

        if retry_timeout is None:  # use exponential backoff
            if attempt_number > 1:
                time_to_sleep = 2**(attempt_number-2)
            else:
                time_to_sleep = 0

        elif isinstance(retry_timeout, (int, float)):  # valid timeout value
            time_to_sleep = retry_timeout
        else:
            time_to_sleep = -1  # wait for user input

        must_sleep = time_to_sleep >= 0
        if must_sleep:
            sleep_text = '(sleep for {}s or press Enter)'.format(time_to_sleep)
        else:
            sleep_text = ''

        retry_text = 'Retry #{} {}. {} ({})'.format(
            attempt_number, sleep_text, error, error.__class__.__name__)


        log(
            'warning',
            text + [retry_text]
        )

        if isinstance(error, UnexpectedHTML):
            log(
                'debug',
                error.html
            )


        if must_sleep:
            # time.sleep(time_to_sleep)
            timed_input(time_to_sleep)
        else:
            pause()

    @staticmethod
    def check_for_invalid_types(messages_types_to_add, allowed_message_types):
        invalid_types = set(messages_types_to_add) - set(allowed_message_types)
        if invalid_types:
            raise InvalidParameter(
                'Invalid types specified: {}'.format(invalid_types))

    @staticmethod
    def get_mapped_keys(remapping):
        mapped_keys = set()
        for key in remapping:
            value = remapping[key]
            if isinstance(remapping[key], tuple):
                value = value[0]
            mapped_keys.add(value)
        return mapped_keys
