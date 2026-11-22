/* A stand-in for Valve's steam_api, for testing what NativeSteam does with
 * what it is given.
 *
 * It exports the flat functions NativeSteam loads, and a few `fake_*`
 * functions a test calls through ctypes to choose what Steam hands back:
 * callbacks of any id and size, a receive count larger than asked for,
 * null interfaces and strings. It records what NativeSteam did with them --
 * messages released, callbacks freed, a callback read before the last was
 * freed -- for the test to check.
 *
 * Built by tests/test_native_steam_hostile.py with the system C compiler.
 */

#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#define EXPORT __attribute__((visibility("default")))

#define MAX_CALLBACKS 64
#define MAX_PARAM 1024

typedef struct {
    int user;
    int callback;
    uint8_t *param;
    int param_bytes;
} CallbackMsg;

typedef struct {
    int id;
    int size;
    uint8_t param[MAX_PARAM];
} Queued;

static Queued queue[MAX_CALLBACKS];
static int queued;
static int next_callback;
static bool holding;

static int frees;
static int reads_while_held;
static int released;
static int receive_extra;
static int received_messages;
static bool null_user, null_utils, null_persona, null_apps;
static char language_buffer[128] = "english";
static const char *language = language_buffer;

static uint64_t next_call = 100;
static int result_size;
static uint8_t result[MAX_PARAM];

/* What the test controls. */

/* The game language Steam reports, or NULL; and whether ISteamApps is null. */
EXPORT void fake_language(const char *name, int null_interface) {
    if (name == NULL) {
        language = NULL;
    } else {
        strncpy(language_buffer, name, sizeof language_buffer - 1);
        language_buffer[sizeof language_buffer - 1] = '\0';
        language = language_buffer;
    }
    null_apps = null_interface;
}

EXPORT void fake_reset(void) {
    queued = next_callback = frees = reads_while_held = released = 0;
    receive_extra = received_messages = result_size = 0;
    holding = null_user = null_utils = null_persona = null_apps = false;
    strcpy(language_buffer, "english");
    language = language_buffer;
    next_call = 100;
}

EXPORT void fake_null(int user, int utils, int persona) {
    null_user = user;
    null_utils = utils;
    null_persona = persona;
}

EXPORT void fake_queue(int id, const uint8_t *param, int size) {
    Queued *entry = &queue[queued++];
    entry->id = id;
    entry->size = size;
    memcpy(entry->param, param, size > MAX_PARAM ? MAX_PARAM : size);
}

/* The next call handle a request returns, and the result it completes with. */
EXPORT uint64_t fake_next_call(void) { return next_call; }

EXPORT void fake_result(const uint8_t *param, int size) {
    result_size = size;
    memcpy(result, param, size > MAX_PARAM ? MAX_PARAM : size);
}

/* Messages waiting, and how many more than asked for receive claims. */
EXPORT void fake_messages(int count, int extra) {
    received_messages = count;
    receive_extra = extra;
}

EXPORT int fake_frees(void) { return frees; }
EXPORT int fake_reads_while_held(void) { return reads_while_held; }
EXPORT int fake_released(void) { return released; }

/* steam_api_flat.h. */

static int dummy_interface;
#define INTERFACE ((void *)&dummy_interface)

EXPORT int SteamAPI_InitFlat(char *error) { (void)error; return 0; }
EXPORT void SteamAPI_Shutdown(void) {}
EXPORT void SteamAPI_ManualDispatch_Init(void) {}
EXPORT void SteamAPI_ManualDispatch_RunFrame(int pipe) { (void)pipe; }

EXPORT bool SteamAPI_ManualDispatch_GetNextCallback(int pipe, CallbackMsg *message) {
    (void)pipe;
    if (holding) reads_while_held++;
    if (next_callback >= queued) return false;
    Queued *entry = &queue[next_callback++];
    message->user = 1;
    message->callback = entry->id;
    message->param = entry->param;
    message->param_bytes = entry->size;
    holding = true;
    return true;
}

EXPORT void SteamAPI_ManualDispatch_FreeLastCallback(int pipe) {
    (void)pipe;
    holding = false;
    frees++;
}

EXPORT bool SteamAPI_ManualDispatch_GetAPICallResult(
    int pipe, uint64_t call, void *out, int size, int expected, bool *failed) {
    (void)pipe; (void)call; (void)expected;
    memcpy(out, result, size < result_size ? size : result_size);
    *failed = false;
    return true;
}

EXPORT int SteamAPI_GetHSteamPipe(void) { return 1; }
EXPORT void *SteamAPI_SteamUser_v023(void) { return null_user ? NULL : INTERFACE; }
EXPORT uint64_t SteamAPI_ISteamUser_GetSteamID(void *self) { (void)self; return 76561197960265729ULL; }
EXPORT void *SteamAPI_SteamFriends_v018(void) { return INTERFACE; }
EXPORT const char *SteamAPI_ISteamFriends_GetPersonaName(void *self) {
    (void)self;
    return null_persona ? NULL : "Fake Player";
}
EXPORT void *SteamAPI_SteamNetworkingMessages_SteamAPI_v002(void) { return INTERFACE; }

EXPORT int SteamAPI_ISteamNetworkingMessages_SendMessageToUser(
    void *self, const void *identity, const void *data, uint32_t size, int flags, int channel) {
    (void)self; (void)identity; (void)data; (void)size; (void)flags; (void)channel;
    return 1;
}

/* A message as SteamNetworkingMessage_t lays it out: data at 0, size at 8,
 * the peer's identity at 16, whose first 8 bytes hold the Steam ID here. */
EXPORT int SteamAPI_ISteamNetworkingMessages_ReceiveMessagesOnChannel(
    void *self, int channel, void **out, int max) {
    (void)self; (void)channel;
    int count = received_messages < max ? received_messages : max;
    for (int i = 0; i < count; i++) {
        uint8_t *message = calloc(1, 16 + 136);
        uint8_t *data = malloc(1);
        data[0] = (uint8_t)i;
        int size = 1;
        uint64_t peer = 1000 + (uint64_t)i;
        memcpy(message, &data, sizeof data);
        memcpy(message + 8, &size, sizeof size);
        memcpy(message + 16, &peer, sizeof peer);
        out[i] = message;
    }
    received_messages -= count;
    return count + receive_extra;
}

EXPORT bool SteamAPI_ISteamNetworkingMessages_AcceptSessionWithUser(void *self, const void *identity) {
    (void)self; (void)identity; return true;
}
EXPORT bool SteamAPI_ISteamNetworkingMessages_CloseSessionWithUser(void *self, const void *identity) {
    (void)self; (void)identity; return true;
}

EXPORT void SteamAPI_SteamNetworkingMessage_t_Release(void *message) {
    uint8_t *data;
    memcpy(&data, message, sizeof data);
    free(data);
    free(message);
    released++;
}

EXPORT void *SteamAPI_SteamNetworkingUtils_SteamAPI_v004(void) { return null_utils ? NULL : INTERFACE; }
EXPORT void SteamAPI_ISteamNetworkingUtils_InitRelayNetworkAccess(void *self) { (void)self; }

EXPORT void SteamAPI_SteamNetworkingIdentity_SetSteamID64(void *identity, uint64_t id) {
    memcpy(identity, &id, sizeof id);
}
EXPORT uint64_t SteamAPI_SteamNetworkingIdentity_GetSteamID64(const void *identity) {
    uint64_t id;
    memcpy(&id, identity, sizeof id);
    return id;
}

EXPORT void *SteamAPI_SteamMatchmaking_v009(void) { return INTERFACE; }
EXPORT uint64_t SteamAPI_ISteamMatchmaking_CreateLobby(void *self, int type, int max) {
    (void)self; (void)type; (void)max; return next_call++;
}
EXPORT uint64_t SteamAPI_ISteamMatchmaking_JoinLobby(void *self, uint64_t lobby) {
    (void)self; (void)lobby; return next_call++;
}
EXPORT void SteamAPI_ISteamMatchmaking_LeaveLobby(void *self, uint64_t lobby) { (void)self; (void)lobby; }
EXPORT uint64_t SteamAPI_ISteamMatchmaking_GetLobbyOwner(void *self, uint64_t lobby) { (void)self; return lobby; }
EXPORT int SteamAPI_ISteamMatchmaking_GetNumLobbyMembers(void *self, uint64_t lobby) {
    (void)self; (void)lobby; return 0;
}
EXPORT uint64_t SteamAPI_ISteamMatchmaking_GetLobbyMemberByIndex(void *self, uint64_t lobby, int i) {
    (void)self; (void)lobby; (void)i; return 0;
}
EXPORT const char *SteamAPI_ISteamMatchmaking_GetLobbyData(void *self, uint64_t lobby, const char *key) {
    (void)self; (void)lobby; (void)key; return "";
}
EXPORT bool SteamAPI_ISteamMatchmaking_SetLobbyData(void *self, uint64_t lobby, const char *key, const char *value) {
    (void)self; (void)lobby; (void)key; (void)value; return true;
}
EXPORT bool SteamAPI_ISteamFriends_SetRichPresence(void *self, const char *key, const char *value) {
    (void)self; (void)key; (void)value; return true;
}
EXPORT void SteamAPI_ISteamFriends_ClearRichPresence(void *self) { (void)self; }
EXPORT void SteamAPI_ISteamFriends_ActivateGameOverlayInviteDialog(void *self, uint64_t lobby) {
    (void)self; (void)lobby;
}

EXPORT void *SteamAPI_SteamApps_v009(void) { return null_apps ? NULL : INTERFACE; }
EXPORT const char *SteamAPI_ISteamApps_GetCurrentGameLanguage(void *self) {
    (void)self;
    return language;
}
