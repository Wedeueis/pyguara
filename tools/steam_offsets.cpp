// Print the Steamworks layouts `rust/src/steam.rs` reads, from an SDK's headers.
//
// Rerun when the SDK changes, and compare with the constants at the top of
// steam.rs. The headers are Valve's and are not in this repository:
//
//   g++ -std=c++17 -w -I<sdk>/public tools/steam_offsets.cpp -o /tmp/off && /tmp/off
//
// That prints Linux's layout (callbacks packed to 4). Undefining the Linux
// macros makes the headers choose Windows' packing (8) for the same compiler:
//
//   g++ -std=c++17 -w -U__linux__ -U__linux -Ulinux -U__gnu_linux__ ...
#include <cstdio>
#include <cstddef>
#include "steam/steam_api.h"
#include "steam/isteamnetworkingmessages.h"
#define O(t, f) printf("%-48s %4zu\n", #t "::" #f, offsetof(t, f))
#define Z(t) printf("%-48s %4zu\n", "sizeof " #t, sizeof(t))
int main() {
  O(CallbackMsg_t, m_iCallback); O(CallbackMsg_t, m_pubParam); O(CallbackMsg_t, m_cubParam); Z(CallbackMsg_t);
  O(SteamAPICallCompleted_t, m_hAsyncCall); O(SteamAPICallCompleted_t, m_iCallback); O(SteamAPICallCompleted_t, m_cubParam); Z(SteamAPICallCompleted_t);
  O(LobbyCreated_t, m_eResult); O(LobbyCreated_t, m_ulSteamIDLobby); Z(LobbyCreated_t);
  O(LobbyEnter_t, m_ulSteamIDLobby); O(LobbyEnter_t, m_EChatRoomEnterResponse); Z(LobbyEnter_t);
  O(LobbyChatUpdate_t, m_ulSteamIDLobby); O(LobbyChatUpdate_t, m_ulSteamIDUserChanged); O(LobbyChatUpdate_t, m_rgfChatMemberStateChange); Z(LobbyChatUpdate_t);
  O(GameLobbyJoinRequested_t, m_steamIDLobby); Z(GameLobbyJoinRequested_t);
  O(GameRichPresenceJoinRequested_t, m_steamIDFriend); O(GameRichPresenceJoinRequested_t, m_rgchConnect); Z(GameRichPresenceJoinRequested_t);
  O(SteamNetworkingMessagesSessionRequest_t, m_identityRemote); Z(SteamNetworkingMessagesSessionRequest_t);
  O(SteamNetworkingMessagesSessionFailed_t, m_info); Z(SteamNetworkingMessagesSessionFailed_t);
  O(SteamNetConnectionInfo_t, m_identityRemote); O(SteamNetConnectionInfo_t, m_eEndReason); O(SteamNetConnectionInfo_t, m_szEndDebug);
  O(SteamNetworkingMessage_t, m_pData); O(SteamNetworkingMessage_t, m_cbSize); O(SteamNetworkingMessage_t, m_identityPeer);
  Z(SteamNetworkingIdentity);
  printf("callback ids: completed %d enter %d created %d chat %d joinreq %d rpjoin %d sreq %d sfail %d\n",
    SteamAPICallCompleted_t::k_iCallback, LobbyEnter_t::k_iCallback, LobbyCreated_t::k_iCallback, LobbyChatUpdate_t::k_iCallback,
    GameLobbyJoinRequested_t::k_iCallback, GameRichPresenceJoinRequested_t::k_iCallback,
    SteamNetworkingMessagesSessionRequest_t::k_iCallback, SteamNetworkingMessagesSessionFailed_t::k_iCallback);
  printf("consts: errmsg %d rpvalue %d rpkey %d lobbykey %d sendrel %d sendunrel %d autorestart %d\n", k_cchMaxSteamErrMsg, k_cchMaxRichPresenceValueLength,
    k_cchMaxRichPresenceKeyLength, k_nMaxLobbyKeyLength, k_nSteamNetworkingSend_ReliableNoNagle, k_nSteamNetworkingSend_UnreliableNoNagle, k_nSteamNetworkingSend_AutoRestartBrokenSession);
  printf("enter states: entered %d left %d disc %d kicked %d banned %d friendsonly %d\n", k_EChatMemberStateChangeEntered, k_EChatMemberStateChangeLeft,
    k_EChatMemberStateChangeDisconnected, k_EChatMemberStateChangeKicked, k_EChatMemberStateChangeBanned, k_ELobbyTypeFriendsOnly);
}
