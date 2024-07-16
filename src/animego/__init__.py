import asyncio
import json
import os
import bs4
import inquirer
import aiohttp
from pprint import pprint
import furl

async def ajax(referer, url, appear_params) -> str:
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.142.86 Safari/537.36"
    HEADERS = {
        "User-Agent": USER_AGENT,
        "X-Requested-With": "XMLHttpRequest",
        "Referer": referer,
        # "Content-Type": "application/json; charset=UTF-8",
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=appear_params, headers=HEADERS) as response:
            # pprint(response)
            return await response.text()

async def iframe(base_url, url, params) -> str:
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.142.86 Safari/537.36"
    HEADERS = {
        "User-Agent": USER_AGENT,
        "Sec-Fetch-Dest": "iframe",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "cross-site",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
        "Referer": base_url,
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params, headers=HEADERS) as response:
            return await response.text()

async def parse_player_info(player_info) -> list:
    soup = bs4.BeautifulSoup(player_info, "html.parser")

    series_tag = soup.select_one("select[name=series]")
    assert series_tag is not None

    series = []
    for option in series_tag.select("option"):
        series.append({"name": option.get_text(), "id": option.attrs.get("value")})

    return series

async def parse_seria_info(seria_info) -> dict:
    soup = bs4.BeautifulSoup(seria_info, "html.parser")
    info = {
        "dubbings": [],
        "players": [],
    }

    dubbings_tag = soup.select_one("#video-dubbing")
    assert dubbings_tag is not None

    for dubbing_tag in dubbings_tag.select("span[data-dubbing]"):
        dubbing_id = dubbing_tag.attrs.get("data-dubbing")
        dubbing_name = dubbing_tag.get_text()

        info["dubbings"].append({"id": dubbing_id, "name": dubbing_name.strip()})
    
    video_players_tag = soup.select_one("#video-players")
    assert video_players_tag is not None

    for video_player_tag in video_players_tag.select("span[data-player]"):
        video_player_id = video_player_tag.attrs.get("data-provider")
        if video_player_id != "24":
            continue

        video_player_name = video_player_tag.get_text()

        info["players"].append({
            "id": video_player_id,
            "name": video_player_name.strip(),
            "url": video_player_tag.attrs.get("data-player"),
            "dubbing": video_player_tag.attrs.get("data-provide-dubbing"),
        })

    return info

async def pick_anime(name: str) -> str:
    base_url = f"https://animego.org/search/anime?q={name}"

    animes = []

    async with aiohttp.ClientSession() as session:
        async with session.get(base_url) as response:
            soup = bs4.BeautifulSoup(await response.text(), "html.parser")
            for tag in soup.select(".animes-grid-item"):

                name_tag = tag.select_one(".animes-grid-item-body > .card-title > a")
                if name_tag is None:
                    continue
                name = name_tag.get_text()
                url_tag = tag.select_one(".animes-grid-item-picture > a")
                if url_tag is None:
                    continue
                url = url_tag.attrs.get("href")

                animes.append({"name": name, "url": url})
                  
    choise =  inquirer.prompt([inquirer.List("anime", message="Anime", choices=[x["name"] for x in animes])])["anime"] # type: ignore

    return animes[[x["name"] for x in animes].index(choise)]["url"]

async def async_main() -> None:
    url = inquirer.prompt([inquirer.Text("url", message="URL or name")])["url"]  # type: ignore
    
    if not url.startswith("https://"):
        url = await pick_anime(url)

    if not url.startswith("https://"):
        raise ValueError("Invalid URL")

    host = url.split("/")[2]
    anime_id = url.split("-")[-1]

    player_info = json.loads(
        await ajax(url, f"https://{host}/anime/{anime_id}/player", {"allow": "true"})
    )

    player_info_content = player_info["content"]
    assert player_info_content is not None

    series = await parse_player_info(player_info_content)
    series = sorted(series, key=lambda x: x["name"])

    selected_episode = inquirer.prompt(
        [
            inquirer.List(
                "episode", message="Episode", choices=[x["name"] for x in series]
            )
        ]
    )["episode"]  # type: ignore
    episode = [x for x in series if x["name"] == selected_episode][0]

    seria_info_json = json.loads(
        await ajax(
            url,
            f"https://{host}/anime/series",
            {"id": episode["id"]},
        )
    )

    seria_info = await parse_seria_info(seria_info_json["content"])

    selected_dubbing = inquirer.prompt(
        [
            inquirer.List(
                "dubbing", message="Dubbing", choices=[x["name"] for x in seria_info["dubbings"] if x["id"] in [i["dubbing"] for i in seria_info["players"]]]
            )
        ]
    )["dubbing"]  # type: ignore
    dubbing = [x for x in seria_info["dubbings"] if x["name"] == selected_dubbing][0]
    player = [x for x in seria_info["players"] if x["dubbing"] == dubbing["id"]][0]

    player_url = furl.furl(f"https::{player["url"]}")
    params = player_url.args

    com_url = f"https{player_url.path}"
    iframe_content = await iframe(f"https://{host}/", com_url, params)

    soup = bs4.BeautifulSoup(iframe_content, "html.parser")
    target_div = soup.select_one("div[data-parameters]")
    assert target_div is not None

    params = target_div.attrs.get("data-parameters")
    assert params is not None

    target_info = json.loads(params)
    hls = json.loads(target_info["hls"])
    assert hls is not None

    src = hls["src"]
    assert src is not None

    os.system("mpv " + src)
    
def main() -> None:
    asyncio.run(async_main())
