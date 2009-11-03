/* getters */
get_map = function() {
    $.getJSON("api/world/map.json", function(map){
        document.map = map;
    });
}

get_player = function() {
    $.getJSON("/api/players/me.json", function(player) {
        document.player = player;
    });
}

/* modifiers */

modify_player = function(data) {
    $.ajax({
        type: "PUT",
        url: "/api/players/me.json",
        data: data,
        dataType: "json",
        success: function(player) {
            document.player = player
        }
    });
}

modify_room = function(data) {
    $.ajax({
        type: "PUT",
        url: "/api/world/rooms/" + data.id + ".json",
        data: data,
        dataType: "json",
        success: function(room) {
            document.player.room = room;
            render_room();
            get_map();
        }
    });
}

move_to = function(x, y) {
    $.ajax({
        type: "PUT",
        url: "/api/players/me.json",
        data: { xpos: x, ypos: y },
        dataType: "json",
        success: function(player) {
            document.player = player;
            render_room();
            get_map();
        }
    });
}

/* deleters */
delete_room = function(data) {
        $.ajax({
            type: "DELETE",
            url: "api/world/rooms/" + data.id + ".json",
            dataType: "json",
        });
}


