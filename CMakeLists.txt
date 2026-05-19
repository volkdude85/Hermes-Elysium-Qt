cmake_minimum_required(VERSION 3.16)
project(HermesElysium LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTORCC ON)

find_package(Qt6 REQUIRED COMPONENTS Widgets DBus)

# QTermWidget 6
find_package(PkgConfig REQUIRED)
pkg_check_modules(QTERMWIDGET6 REQUIRED qtermwidget6)

add_library(hermes_terminal SHARED
    src/terminal_panel.cpp
)

target_include_directories(hermes_terminal PRIVATE
    ${QTERMWIDGET6_INCLUDE_DIRS}
)

target_link_libraries(hermes_terminal PRIVATE
    Qt6::Widgets
    Qt6::DBus
    ${QTERMWIDGET6_LIBRARIES}
)

target_compile_options(hermes_terminal PRIVATE
    ${QTERMWIDGET6_CFLAGS_OTHER}
)
